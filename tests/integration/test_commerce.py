from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.models import AIOperation, CommerceOrder, Membership, Resume, utcnow
from app.services import commerce
from app.services.errors import BusinessError
from tests.integration.test_mysql import login_client

pytestmark = pytest.mark.integration


@pytest.fixture
def checkout(mysql_app, user_factory):
    uid, _ = user_factory()
    mysql_app.config["MOCK_PAYMENT_ENABLED"] = True
    return uid


def test_fixed_monthly_and_quarterly_memberships(mysql_app, checkout):
    uid = checkout
    with mysql_app.app_context():
        monthly = commerce.create_order(uid, uuid4(), "membership_monthly")
        assert monthly.price_yuan == Decimal("39.00")
        assert monthly.period_days == 30
        assert monthly.credits == 0
        assert commerce.settle_mock(uid, monthly.id, "success").state == "paid"
        membership = db.session.get(Membership, uid)
        monthly_expiry = membership.expires_at
        assert membership.plan_code == "membership_monthly"

        quarterly = commerce.create_order(uid, uuid4(), "membership_quarterly")
        assert quarterly.price_yuan == Decimal("99.00")
        assert quarterly.period_days == 90
        commerce.settle_mock(uid, quarterly.id, "success")
        assert membership.plan_code == "membership_quarterly"
        assert membership.expires_at == monthly_expiry + timedelta(days=90)


def test_free_limits_and_member_entitlements(mysql_app, checkout):
    uid = checkout
    with mysql_app.app_context():
        assert commerce.entitlements(uid)["can_create_resume"]
        for index in range(2):
            db.session.add(Resume(user_id=uid, request_key=str(uuid4()), title=f"Resume {index}"))
        db.session.commit()
        assert commerce.entitlements(uid)["resume_count"] == 2
        with pytest.raises(BusinessError) as error:
            commerce.ensure_resume_capacity(uid)
        assert error.value.status == 409

        first_resume = db.session.scalar(select(Resume).where(Resume.user_id == uid))
        for _ in range(5):
            db.session.add(
                AIOperation(
                    user_id=uid,
                    resume_id=first_resume.id,
                    request_key=str(uuid4()),
                    kind="optimize",
                    state="succeeded",
                    diagnostic_revision=1,
                    ceiling=0,
                    input_snapshot={},
                    expires_at=utcnow() + timedelta(minutes=10),
                )
            )
        db.session.commit()
        assert commerce.entitlements(uid)["resume_ai_remaining"] == 0
        with pytest.raises(BusinessError) as error:
            commerce.ensure_resume_ai_capacity(uid)
        assert error.value.status == 403
        commerce.ensure_job_analysis_capacity(uid)
        assert commerce.entitlements(uid)["analysis_remaining"] == 1

        order = commerce.create_order(uid, uuid4(), "membership_quarterly")
        commerce.settle_mock(uid, order.id, "success")
        assert commerce.entitlements(uid)["is_member"]
        assert commerce.entitlements(uid)["resume_ai_remaining"] is None
        assert commerce.entitlements(uid)["can_create_resume"]
        assert commerce.entitlements(uid)["can_export_resume"]
        commerce.ensure_resume_ai_capacity(uid)
        commerce.ensure_job_analysis_capacity(uid)

        for index in range(8):
            db.session.add(Resume(user_id=uid, request_key=str(uuid4()), title=f"More {index}"))
        db.session.commit()
        assert commerce.entitlements(uid)["resume_count"] == 10
        with pytest.raises(BusinessError, match="10"):
            commerce.ensure_resume_capacity(uid)


def test_failed_checkout_and_request_key_idempotency(mysql_app, checkout):
    uid = checkout
    with mysql_app.app_context():
        key = uuid4()
        order = commerce.create_order(uid, key, "membership_monthly")
        assert commerce.create_order(uid, key, "membership_monthly").id == order.id
        with pytest.raises(BusinessError):
            commerce.create_order(uid, key, "membership_quarterly")
        db.session.rollback()
        assert commerce.settle_mock(uid, order.id, "failure").state == "failed"
        with pytest.raises(BusinessError):
            commerce.settle_mock(uid, order.id, "success")
        db.session.rollback()
        assert db.session.get(Membership, uid) is None


def test_checkout_page_and_single_step_local_activation(mysql_app, checkout):
    client, _ = login_client(mysql_app, checkout)
    page = client.get("/workspace?view=billing")
    assert page.status_code == 200
    assert "39" in page.text
    assert "99" in page.text
    assert "首次" in page.text and "PDF" in page.text
    csrf = page.text.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    response = client.post(
        "/commerce/orders",
        data={
            "csrf_token": csrf,
            "request_key": str(uuid4()),
            "plan_code": "membership_quarterly",
        },
    )
    assert response.status_code == 303
    billing_page = client.get("/workspace?view=billing").text
    assert "积分" not in billing_page and "点数" not in billing_page
    with mysql_app.app_context():
        membership = db.session.get(Membership, checkout)
        assert membership.plan_code == "membership_quarterly"
        assert db.session.scalar(
            select(func.count()).select_from(CommerceOrder).where(
                CommerceOrder.user_id == checkout,
                CommerceOrder.plan_code == "membership_quarterly",
                CommerceOrder.state == "paid",
            )
        ) == 1


def test_free_export_requires_explicit_grant(mysql_app, checkout):
    from app.models import ResumeVersion

    with mysql_app.app_context():
        resume = Resume(user_id=checkout, request_key=str(uuid4()), title="Private Resume")
        db.session.add(resume)
        db.session.flush()
        db.session.add(
            ResumeVersion(
                resume_id=resume.id,
                revision=1,
                request_key=str(uuid4()),
                title=resume.title,
                template="classic",
                document={},
            )
        )
        resume.revision = 1
        resume_id = resume.id
        db.session.commit()
        assert commerce.entitlements(checkout)["can_export_resume"]

    client, _ = login_client(mysql_app, checkout)
    response = client.get(f"/resumes/{resume_id}/print")
    assert response.status_code == 403
