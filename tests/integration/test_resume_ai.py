from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.career_schemas import ResumeSave
from app.extensions import db
from app.models import AIOperation, CreditAccount, CreditEntry
from app.resume_ai_schemas import ResumeAIQuote
from app.services import career, credits, resume_ai
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
        credits.grant(user_id, 100, "experience")
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
        operation_id, ceiling = first.id, first.ceiling
        with pytest.raises(BusinessError) as forbidden:
            quote(other_id, resume_id)
        assert forbidden.value.status == 404
        db.session.rollback()
        assert resume_ai.confirm(user_id, operation_id).state == "queued"
        assert resume_ai.confirm(user_id, operation_id).state == "queued"
        account = db.session.get(CreditAccount, user_id)
        assert account.frozen == ceiling
        assert account.available == 100 - ceiling
        resume_ai.run_operation(operation_id)
        item = db.session.get(AIOperation, operation_id)
        assert item.state == "succeeded" and item.charged > 0
        assert item.result["original"] == "负责产品需求分析"
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(CreditEntry)
                .where(CreditEntry.operation_id == operation_id, CreditEntry.kind == "settle")
            )
            == 1
        )
        assert db.session.get(CreditAccount, user_id).frozen == 0
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
        assert db.session.get(CreditAccount, user_id).available == 100


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
        assert db.session.get(CreditAccount, user_id).available == 100


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


def test_resume_ai_failure_releases_all_credits(mysql_app, resume_context):
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
        balance = db.session.get(CreditAccount, user_id)
        assert (balance.available, balance.frozen) == (100, 0)
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(CreditEntry)
                .where(CreditEntry.operation_id == operation_id, CreditEntry.kind == "release")
            )
            == 1
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
        assert db.session.get(CreditAccount, user_id).available == 100


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
