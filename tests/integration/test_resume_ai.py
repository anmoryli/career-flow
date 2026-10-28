from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.career_schemas import ResumeSave
from app.extensions import db
from app.models import AIOperation, CreditEntry
from app.resume_ai_schemas import ResumeAIQuote, ResumeComposeQuote
from app.services import career, resume_ai
from app.services.errors import BusinessError

pytestmark = pytest.mark.integration


@pytest.fixture
def resume_context(mysql_app, user_factory):
    user_id, _ = user_factory()
    with mysql_app.app_context():
        resume = career.save_resume(
            user_id,
            ResumeSave(
                request_key=uuid4(),
                title="真实简历",
                document={"summary": "负责产品需求分析", "role": "产品经理"},
            ),
        )
        db.session.commit()
    mysql_app.extensions["resume_provider"] = lambda snapshot: (
        {"proposed": "负责产品需求分析与整理", "reason": "语句更清晰"},
        1100,
    )
    yield user_id, resume["id"]
    mysql_app.extensions.pop("resume_provider", None)


def quote(user_id, resume_id, key=None):
    return resume_ai.quote(
        user_id,
        resume_id,
        ResumeAIQuote(request_key=key or uuid4(), revision=1, path="summary", mode="optimize"),
    )


def test_resume_ai_idempotent_quote_settlement_and_ownership(
    mysql_app, resume_context, user_factory
):
    from tests.integration.test_career import client_for

    user_id, resume_id = resume_context
    other_id, _ = user_factory()
    with mysql_app.app_context():
        key = uuid4()
        first = quote(user_id, resume_id, key)
        assert first.input_snapshot["prompt_version"] == "resume-rewrite-1"
        assert quote(user_id, resume_id, key).id == first.id
        operation_id = first.id
        with pytest.raises(BusinessError) as forbidden:
            quote(other_id, resume_id)
        assert forbidden.value.status == 404
        db.session.rollback()
        assert resume_ai.confirm(user_id, operation_id).state == "queued"
        assert resume_ai.confirm(user_id, operation_id).state == "queued"
        assert first.ceiling == 0
        resume_ai.run_operation(operation_id)
        item = db.session.get(AIOperation, operation_id)
        assert item.state == "succeeded" and item.charged == 0
        assert item.result["original"] == "负责产品需求分析"
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(CreditEntry)
                .where(CreditEntry.operation_id == operation_id, CreditEntry.kind == "settle")
            )
            == 0
        )
        assert resume_ai.confirm(user_id, operation_id).state == "succeeded"
    other_client, _ = client_for(mysql_app, other_id)
    assert other_client.get(f"/api/resume-ai/{operation_id}").status_code == 404


def test_resume_ai_rejects_stale_revision_and_missing_entry(mysql_app, resume_context):
    user_id, resume_id = resume_context
    with mysql_app.app_context():
        with pytest.raises(BusinessError) as stale:
            resume_ai.quote(
                user_id,
                resume_id,
                ResumeAIQuote(request_key=uuid4(), revision=2, path="summary", mode="optimize"),
            )
        assert stale.value.status == 409
        db.session.rollback()
        with pytest.raises(BusinessError) as missing:
            resume_ai.quote(
                user_id,
                resume_id,
                ResumeAIQuote(
                    request_key=uuid4(), revision=1, path="experiences.0.bullets.0", mode="generate"
                ),
            )
        assert missing.value.status == 422
        db.session.rollback()
        assert not db.session.scalars(
            select(CreditEntry).where(CreditEntry.user_id == user_id)
        ).all()


def test_resume_ai_queue_failure_releases_reservation(mysql_app, resume_context, monkeypatch):
    from tests.integration.test_career import client_for

    user_id, resume_id = resume_context
    with mysql_app.app_context():
        operation_id = quote(user_id, resume_id).id

    class BrokenQueue:
        def __init__(self, *args, **kwargs):
            pass

        def enqueue(self, *args, **kwargs):
            raise RuntimeError("queue unavailable")

    monkeypatch.setattr("app.web.career.Queue", BrokenQueue)
    client, headers = client_for(mysql_app, user_id)
    response = client.post(f"/api/resume-ai/{operation_id}/confirm", json={}, headers=headers)
    assert response.status_code == 503
    with mysql_app.app_context():
        item = db.session.get(AIOperation, operation_id)
        assert item.state == "cancelled"
        assert not db.session.scalars(
            select(CreditEntry).where(CreditEntry.user_id == user_id)
        ).all()


def test_unconfirmed_quote_does_not_block_resume_deletion(mysql_app, resume_context):
    from tests.integration.test_career import client_for

    user_id, resume_id = resume_context
    with mysql_app.app_context():
        quote(user_id, resume_id)
    client, headers = client_for(mysql_app, user_id)
    response = client.post(
        f"/api/resumes/{resume_id}/delete", json={"confirm": "delete"}, headers=headers
    )
    assert response.status_code == 200


def test_resume_ai_failure_creates_no_credit_entries(mysql_app, resume_context):
    user_id, resume_id = resume_context

    def failing(_snapshot):
        raise TimeoutError("synthetic timeout")

    mysql_app.extensions["resume_provider"] = failing
    with mysql_app.app_context():
        operation_id = quote(user_id, resume_id).id
        resume_ai.confirm(user_id, operation_id)
        resume_ai.run_operation(operation_id)
        item = db.session.get(AIOperation, operation_id)
        assert item.state == "failed" and item.attempts == 2
        assert item.charged == 0
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(CreditEntry)
                .where(CreditEntry.operation_id == operation_id, CreditEntry.kind == "release")
            )
                == 0
        )


def test_resume_ai_rejects_invented_numbers(mysql_app, resume_context):
    user_id, resume_id = resume_context
    mysql_app.extensions["resume_provider"] = lambda _snapshot: (
        {"proposed": "提升业绩 99%", "reason": "错误的虚构数字"},
        500,
    )
    with mysql_app.app_context():
        operation_id = quote(user_id, resume_id).id
        resume_ai.confirm(user_id, operation_id)
        resume_ai.run_operation(operation_id)
        item = db.session.get(AIOperation, operation_id)
        assert item.state == "failed" and item.result is None
        assert not db.session.scalars(
            select(CreditEntry).where(CreditEntry.user_id == user_id)
        ).all()


def test_pasted_resume_compose_is_reviewable_and_billed(mysql_app, resume_context):
    user_id, resume_id = resume_context
    source = "林青，产品经理。2022 年在示例公司负责产品需求分析。"
    mysql_app.extensions["resume_compose_provider"] = lambda _snapshot: (
        {
            "document": {
                "name": "林青",
                "role": "产品经理",
                "experiences": [
                    {"company": "示例公司", "period": "2022", "bullets": ["负责产品需求分析"]}
                ],
            },
            "reason": "请核对经历描述",
        },
        900,
    )
    try:
        with mysql_app.app_context():
            data = ResumeComposeQuote(request_key=uuid4(), revision=1, source=source)
            quoted = resume_ai.quote_compose(user_id, resume_id, data)
            assert resume_ai.quote_compose(user_id, resume_id, data).id == quoted.id
            operation_id = quoted.id
            resume_ai.confirm(user_id, operation_id)
            resume_ai.run_operation(operation_id)
            item = db.session.get(AIOperation, operation_id)
            assert item.state == "succeeded"
            assert item.result["document"]["experiences"][0]["company"] == "示例公司"
            assert career.owned(career.Resume, user_id, resume_id).revision == 1
            assert item.ceiling == 0
    finally:
        mysql_app.extensions.pop("resume_compose_provider", None)


def test_pasted_resume_compose_releases_on_invented_number(mysql_app, resume_context):
    user_id, resume_id = resume_context
    mysql_app.extensions["resume_compose_provider"] = lambda _snapshot: (
        {"document": {"summary": "提升业绩 99%"}, "reason": "测试"},
        500,
    )
    try:
        with mysql_app.app_context():
            item = resume_ai.quote_compose(
                user_id,
                resume_id,
                ResumeComposeQuote(
                    request_key=uuid4(),
                    revision=1,
                    source="负责产品需求分析和整理工作，了解实际流程。",
                ),
            )
            operation_id = item.id
            resume_ai.confirm(user_id, operation_id)
            resume_ai.run_operation(operation_id)
            assert db.session.get(AIOperation, operation_id).state == "failed"
            assert not db.session.scalars(
            select(CreditEntry).where(CreditEntry.user_id == user_id)
        ).all()
    finally:
        mysql_app.extensions.pop("resume_compose_provider", None)


def test_resume_ai_concurrent_worker_runs_once(mysql_app, resume_context):
    user_id, resume_id = resume_context
    calls = []
    lock = Lock()

    def provider(_snapshot):
        with lock:
            calls.append(1)
        sleep(0.15)
        return {"proposed": "负责产品需求分析与整理", "reason": "更清楚"}, 1000

    mysql_app.extensions["resume_provider"] = provider
    with mysql_app.app_context():
        operation_id = quote(user_id, resume_id).id
        resume_ai.confirm(user_id, operation_id)

    def run(_):
        with mysql_app.app_context():
            resume_ai.run_operation(operation_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, range(2)))
    assert len(calls) == 1
    with mysql_app.app_context():
        assert db.session.get(AIOperation, operation_id).state == "succeeded"
