"""Real-MySQL acceptance for the non-payment product release."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.career_schemas import ResumeSave
from app.diagnosis_schemas import QuoteInput
from app.extensions import db
from app.models import Membership, ModelCallUsage, ProductEvent, ReportShare, utcnow
from app.product_schemas import ProductPolicy, ShareInput
from app.resume_templates import TEMPLATE_IDS
from app.services import career, diagnosis, product, product_growth, product_metrics
from app.services.errors import BusinessError
from tests.integration import test_career
from tests.integration.test_career import client_for

context = test_career.context

pytestmark = pytest.mark.integration


def finish(uid, did):
    operation = diagnosis.quote(uid, did, QuoteInput(request_key=uuid4(), kind="analysis"))
    diagnosis.confirm(uid, operation.id)
    diagnosis.run_operation(operation.id)
    db.session.refresh(operation)
    assert operation.state == "succeeded", operation.error
    return operation


def test_free_preview_cannot_bypass_review_report_or_question(mysql_app, context):
    uid, _, jid, did = context
    with mysql_app.app_context():
        db.session.delete(db.session.get(Membership, uid))
        db.session.commit()
        operation = finish(uid, did)
        oid = operation.id
        assert operation.result["suggestions"] == []
        assert operation.result["question"] == ""
        assert product.quota_info(uid)["analysis_remaining"] == 0
        assert product.monthly_usage(uid)["reserved"] == 0
        with pytest.raises(BusinessError, match="额度"):
            diagnosis.quote(uid, did, QuoteInput(request_key=uuid4(), kind="analysis"))
        db.session.rollback()
        with pytest.raises(BusinessError, match="会员"):
            diagnosis.quote(uid, did, QuoteInput(request_key=uuid4(), kind="report"))
        db.session.rollback()
    client, headers = client_for(mysql_app, uid)
    payload = client.get(f"/api/operations/{oid}")
    assert payload.status_code == 200
    assert "suggestions" not in payload.json["result"]
    assert client.get(f"/jobs/{jid}").status_code == 200
    assert client.get(f"/jobs/{jid}/report").status_code == 403
    assert client.post(f"/api/operations/{oid}/apply", json={}, headers=headers).status_code in {
        403,
        404,
        422,
    }


def test_free_pdf_grant_is_serialized_and_same_version_repeatable(mysql_app, user_factory):
    uid, _ = user_factory()
    with mysql_app.app_context():
        original = career.save_resume(
            uid, ResumeSave(request_key=uuid4(), title="合成", document={"name": "合成测试"})
        )
        rid = original["id"]
        career.save_resume(
            uid,
            ResumeSave(
                request_key=uuid4(), revision=1, title="合成第二版", document={"name": "合成测试"}
            ),
            rid,
        )

    def export(revision):
        with mysql_app.app_context():
            try:
                version = career.version_of(
                    career.owned(__import__("app.models", fromlist=["Resume"]).Resume, uid, rid),
                    revision,
                )
                product.authorize_export(uid, version, consume=True)
                return revision, 200
            except BusinessError as error:
                db.session.rollback()
                return revision, error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(export, [1, 2]))
    assert sorted(status for _, status in responses) == [200, 403]
    winner = next(revision for revision, status in responses if status == 200)
    assert export(winner) == (winner, 200)
    client, headers = client_for(mysql_app, uid)
    assert client.get(f"/resumes/{rid}/print?revision={winner}").status_code == 200
    assert (
        client.post(
            f"/api/resumes/{rid}/export",
            json={"request_key": str(uuid4()), "revision": winner},
            headers=headers,
        ).status_code
        == 200
    )
    with mysql_app.app_context():
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(ProductEvent)
                .where(ProductEvent.user_id == uid, ProductEvent.name == "pdf_exported")
            )
            == 1
        )


def test_failure_releases_analysis_quota_and_retry_is_idempotent(mysql_app, context):
    uid, _, _, did = context

    def broken(_snapshot):
        raise TimeoutError("synthetic only")

    mysql_app.extensions["diagnosis_provider"] = broken
    with mysql_app.app_context():
        db.session.delete(db.session.get(Membership, uid))
        db.session.commit()
        key = uuid4()
        data = QuoteInput(request_key=key, kind="analysis")
        operation = diagnosis.quote(uid, did, data)
        assert diagnosis.quote(uid, did, data).id == operation.id
        diagnosis.confirm(uid, operation.id)
        diagnosis.run_operation(operation.id)
        db.session.refresh(operation)
        assert operation.state == "failed" and operation.attempts == 2
        assert product.quota_info(uid)["analysis_remaining"] == 1
        assert product.monthly_usage(uid)["reserved"] == 0
        assert operation.charged == 0


def test_cancelled_calls_still_count_actual_tokens_and_unknown_cost(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        operation = diagnosis.quote(uid, did, QuoteInput(request_key=uuid4(), kind="analysis"))
        operation.state = "cancelled"
        config = ProductPolicy()
        product.store_call_usage(
            operation,
            [
                product.call_usage(
                    1, "test", product.TokenUsage(120, 100, 20), config, "invalid_output"
                )
            ],
            None,
        )
        db.session.commit()
        assert product.monthly_usage(uid)["tokens"] == 120
        assert product.monthly_usage(uid)["reserved"] == 0
        row = db.session.scalar(
            select(ModelCallUsage).where(ModelCallUsage.operation_id == operation.id)
        )
        assert row.estimated_cost_cny is None


def test_member_soft_hard_limits_and_distinct_diagnostic_count(mysql_app, context):
    uid, _, _, did = context
    mysql_app.config["PRODUCT_POLICY"] = {
        "member_analyses_monthly": 1,
        "member_soft_tokens_monthly": 10000,
        "member_hard_tokens_monthly": 100000,
    }
    with mysql_app.app_context():
        op = finish(uid, did)
        op.tokens = 10001
        call = db.session.scalar(select(ModelCallUsage).where(ModelCallUsage.operation_id == op.id))
        call.total_tokens = 10001
        db.session.commit()
        assert product.quota_info(uid)["analysis_remaining"] == 0
        product.ensure_analysis(uid, did)  # Follow-up for same job is not another job.
        with pytest.raises(BusinessError, match="额度"):
            product.ensure_analysis(uid, did + 1000000)
        db.session.rollback()
        with pytest.raises(BusinessError, match="轻量"):
            product.prepare_snapshot(uid, {"model": "test"})
        db.session.rollback()
        mysql_app.config["PRODUCT_POLICY"]["light_model_id"] = "not-configured-model"
        with pytest.raises(BusinessError):
            product.prepare_snapshot(uid, {"model": "test"})
        db.session.rollback()
        mysql_app.config["PRODUCT_POLICY"]["member_hard_tokens_monthly"] = 10001
        with pytest.raises(BusinessError, match="安全上限"):
            product.prepare_snapshot(uid, {"model": "test"})
        db.session.rollback()


def test_share_preview_scope_privacy_owner_expiry_and_revocation(mysql_app, context, user_factory):
    uid, _, _, did = context
    other, _ = user_factory()
    with mysql_app.app_context():
        operation = finish(uid, did)
        operation.result = operation.result | {
            "summary": "PRIVATE SUMMARY",
            "findings": [
                {
                    "category": "missing",
                    "source": "none",
                    "evidence": "PRIVATE EVIDENCE",
                    "requirement": "测试 联系 synthetic@example.com 13800138000",
                    "explanation": "PRIVATE EXPLANATION",
                }
            ],
        }
        db.session.commit()
        data = ShareInput(request_key=uuid4(), confirmed="yes")
        snapshot = product_growth.share_snapshot(operation, data.fields)
        assert set(snapshot) == {"fields", "notice", "overall_score", "dimensions", "gap_count"}
        digest = product_growth.preview_signature(uid, operation.id, data, snapshot)
        with pytest.raises(BusinessError, match="预览"):
            product_growth.create_share(uid, operation.id, data, "bad")
        db.session.rollback()
        share = product_growth.create_share(uid, operation.id, data, digest)
        sid, oid = share.id, operation.id
        token = product_growth.signature(sid)
        assert product_growth.create_share(uid, oid, data, digest).id == sid
        changed = data.model_copy(update={"days": 30})
        with pytest.raises(BusinessError, match="同一请求"):
            product_growth.create_share(
                uid, oid, changed, product_growth.preview_signature(uid, oid, changed, snapshot)
            )
        db.session.rollback()
        assert "@" not in str(product_growth.share_snapshot(operation, ["requirements"]))
        assert "13800138000" not in str(product_growth.share_snapshot(operation, ["requirements"]))
        with pytest.raises(BusinessError) as error:
            product_growth.revoke_share(other, sid)
        assert error.value.status == 404
        db.session.rollback()
    public = mysql_app.test_client()
    response = public.get(f"/s/{sid}/{token}")
    assert response.status_code == 200 and "noindex" in response.headers["X-Robots-Tag"]
    assert "PRIVATE" not in response.text and "synthetic@example.com" not in response.text
    assert public.get(f"/s/{sid}/invalid-token").status_code == 404
    owner, _ = client_for(mysql_app, uid)
    assert owner.get(f"/operations/{oid}/share").status_code == 200
    with mysql_app.app_context():
        product_growth.revoke_share(uid, sid)
    assert public.get(f"/s/{sid}/{token}").status_code == 404
    with mysql_app.app_context():
        share = db.session.get(ReportShare, sid)
        share.revoked_at = None
        share.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
    assert public.get(f"/s/{sid}/{token}").status_code == 404


def test_referral_and_events_are_idempotent_without_rewards(mysql_app, user_factory):
    inviter, _ = user_factory()
    joined, _ = user_factory()
    with mysql_app.app_context():
        code = product_growth.invite_code(inviter).code
        product_growth.attribute_registration(inviter, code)
        product_growth.attribute_registration(joined, code)
        db.session.commit()
        product_growth.attribute_registration(joined, code)
        product.record_event(joined, "resume_saved", "same", resume_id=123)
        product.record_event(joined, "resume_saved", "same", resume_id=123)
        db.session.commit()
        assert (
            db.session.scalar(
                select(func.count())
                .select_from(ProductEvent)
                .where(ProductEvent.user_id == joined, ProductEvent.name == "invitation_registered")
            )
            == 1
        )
        assert db.session.get(Membership, joined) is None
        with pytest.raises(ValueError):
            product.record_event(joined, "resume_saved", "privacy", document="PRIVATE")
    owner, _ = client_for(mysql_app, inviter)
    assert owner.get("/invitations").status_code == 200
    assert mysql_app.test_client().get(f"/invite/{code}").status_code == 303


def test_all_eight_templates_save_render_export_and_seo(mysql_app, context):
    uid, rid, _, _ = context
    client, headers = client_for(mysql_app, uid)
    with mysql_app.app_context():
        for revision, template in enumerate(TEMPLATE_IDS, start=1):
            result = career.save_resume(
                uid,
                ResumeSave(
                    request_key=uuid4(),
                    revision=revision,
                    title="合成版式",
                    template=template,
                    document={
                        "name": "合成测试",
                        "summary": "真实内容不翻译",
                        "hidden_sections": ["education"],
                    },
                ),
                rid,
            )
            assert result["template"] == template
            page = client.get(f"/resumes/{rid}/print?revision={revision + 1}")
            assert page.status_code == 200 and "真实内容不翻译" in page.text
    assert client.get(f"/workspace?view=resume-new&resume_id={rid}").status_code == 200
    public = mysql_app.test_client()
    assert public.get("/guides").status_code == 200
    from app.product_content import GUIDES

    for guide in GUIDES:
        page = public.get(f"/guides/{guide}")
        assert page.status_code == 200
        assert 'rel="canonical"' in page.text
    assert public.get("/sitemap.xml").status_code == 200
    assert "Disallow: /api/" in public.get("/robots.txt").text


def test_metrics_mock_revenue_unknown_and_real_price_calculation(mysql_app, context):
    uid, _, _, did = context
    with mysql_app.app_context():
        operation = finish(uid, did)
        config = ProductPolicy(
            model_prices={
                "synthetic": {"input_per_million_cny": "1", "output_per_million_cny": "2"}
            }
        )
        record = product.call_usage(
            2, "synthetic", product.TokenUsage(1000000, 800000, 200000), config, "succeeded"
        )
        assert record["estimated_cost_cny"] == Decimal("1.200000")
        product.store_call_usage(operation, [record], None)
        product.record_event(
            uid, "membership_activated", "synthetic-mock", payment_mode="mock", amount_minor=3900
        )
        db.session.commit()
        stats = product_metrics.metrics()
        assert stats["real_arpu_cny"] is None
        assert stats["ai_cost_to_arpu_ratio"] is None
