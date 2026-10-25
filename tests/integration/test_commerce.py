import re
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.admin_schemas import CommerceSettings
from app.extensions import db
from app.models import CommerceOrder, CreditEntry, Membership, MembershipCycle, utcnow
from app.services import admin_config, commerce, credits
from app.services.errors import BusinessError
from tests.integration.test_admin import commerce_settings
from tests.integration.test_mysql import login_client

pytestmark = pytest.mark.integration


@pytest.fixture
def checkout(mysql_app, user_factory, monkeypatch):
    uid, _ = user_factory()
    mysql_app.config["MOCK_PAYMENT_ENABLED"] = True
    def published():
        return CommerceSettings.model_validate(commerce_settings()), None

    monkeypatch.setattr(commerce, "runtime_commerce", published)
    monkeypatch.setattr(admin_config, "runtime_commerce", published)
    yield uid


def test_credit_order_snapshot_failure_retry_and_idempotent_grant(mysql_app, checkout):
    uid = checkout
    with mysql_app.app_context():
        key = uuid4()
        order = commerce.create_order(uid, key, "credit_pack_1")
        assert order.price_yuan == Decimal("9.90")
        assert commerce.create_order(uid, key, "credit_pack_1").id == order.id
        with pytest.raises(BusinessError, match="更换套餐"):
            commerce.create_order(uid, key, "credit_pack_2")
        db.session.rollback()
        assert commerce.settle_mock(uid, order.id, "failure").state == "failed"
        assert commerce.settle_mock(uid, order.id, "failure").state == "failed"
        with pytest.raises(BusinessError, match="不能更改"):
            commerce.settle_mock(uid, order.id, "success")
        db.session.rollback()

        paid = commerce.create_order(uid, uuid4(), "credit_pack_1")
        assert commerce.settle_mock(uid, paid.id, "success").state == "paid"
        assert commerce.settle_mock(uid, paid.id, "success").state == "paid"
        assert credits.category_balances(uid) == {"purchased": (100, 0)}
        assert db.session.scalar(
            select(func.count())
            .select_from(CreditEntry)
            .where(CreditEntry.source_order_id == paid.id)
        ) == 1


def test_membership_cycles_renewal_and_scheduled_grant(mysql_app, checkout, monkeypatch):
    uid = checkout
    with mysql_app.app_context():
        order = commerce.create_order(uid, uuid4(), "membership_90")
        commerce.settle_mock(uid, order.id, "success")
        cycles = db.session.scalars(
            select(MembershipCycle)
            .where(MembershipCycle.user_id == uid)
            .order_by(MembershipCycle.starts_at)
        ).all()
        assert len(cycles) == 3
        assert cycles[0].credits == cycles[1].credits == cycles[2].credits == 30
        assert credits.category_balances(uid) == {"member": (30, 0)}
        first_expiry = db.session.get(Membership, uid).expires_at
        renewal = commerce.create_order(uid, uuid4(), "membership_30")
        commerce.settle_mock(uid, renewal.id, "success")
        assert db.session.get(Membership, uid).expires_at == first_expiry + timedelta(days=30)
        assert credits.category_balances(uid) == {"member": (30, 0)}

        # Move only the next scheduled cycle into the past to exercise its due path.
        moment = utcnow()
        cycles[1].starts_at = moment - timedelta(minutes=1)
        cycles[0].ends_at = moment - timedelta(minutes=2)
        db.session.get(Membership, uid).next_grant_at = cycles[1].starts_at
        db.session.commit()
        assert commerce.grant_due(uid) == 1
        db.session.commit()
        assert commerce.grant_due(uid) == 0
        assert credits.category_balances(uid) == {"member": (60, 0)}


def test_checkout_is_private_and_disabled_in_production(mysql_app, checkout, user_factory):
    uid = checkout
    other_uid, _ = user_factory()
    with mysql_app.app_context():
        order = commerce.create_order(uid, uuid4(), "credit_pack_1")
        with pytest.raises(BusinessError) as error:
            commerce.settle_mock(other_uid, order.id, "success")
        assert error.value.status == 404
        db.session.rollback()
        mysql_app.config["MOCK_PAYMENT_ENABLED"] = False
        with pytest.raises(BusinessError) as error:
            commerce.create_order(uid, uuid4(), "credit_pack_1")
        assert error.value.status == 403
        db.session.rollback()
        mysql_app.config["MOCK_PAYMENT_ENABLED"] = True
        mysql_app.config["APP_ENV"] = "production"
        with pytest.raises(BusinessError) as error:
            commerce.settle_mock(uid, order.id, "success")
        assert error.value.status == 403


def test_billing_page_checkout_payment_and_csrf(mysql_app, checkout, user_factory):
    uid = checkout
    client, _ = login_client(mysql_app, uid)
    page = client.get("/workspace?view=billing")
    assert page.status_code == 200
    assert "30 天会员" in page.text and "¥19.90" in page.text
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    key = str(uuid4())
    payload = {"csrf_token": csrf, "request_key": key, "plan_code": "credit_pack_1"}
    assert client.post("/commerce/orders", data=payload).status_code == 303
    assert client.post("/commerce/orders", data=payload).status_code == 303
    with mysql_app.app_context():
        order = db.session.scalar(
            select(CommerceOrder).where(CommerceOrder.user_id == uid)
        )
        assert order.price_yuan == Decimal("9.90") and order.state == "pending"
        order_id = order.id
    assert client.post(
        f"/commerce/orders/{order_id}/mock-payment", data={"outcome": "success"}
    ).status_code == 400
    other_uid, _ = user_factory()
    other, _ = login_client(mysql_app, other_uid)
    other_csrf = re.search(
        r'name="csrf_token" value="([^"]+)"',
        other.get("/workspace?view=billing").text,
    ).group(1)
    assert other.post(
        f"/commerce/orders/{order_id}/mock-payment",
        data={"csrf_token": other_csrf, "outcome": "success"},
    ).status_code == 404
    payment = {"csrf_token": csrf, "outcome": "success"}
    assert client.post(f"/commerce/orders/{order_id}/mock-payment", data=payment).status_code == 303
    assert client.post(f"/commerce/orders/{order_id}/mock-payment", data=payment).status_code == 303
    assert "模拟成功" in client.get("/workspace?view=billing").text
