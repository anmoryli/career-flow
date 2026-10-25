from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.admin_schemas import CommerceSettings
from app.extensions import db
from app.models import CommerceOrder, CreditEntry, Membership, MembershipCycle, utcnow
from app.services import commerce, credits
from app.services.errors import BusinessError
from tests.integration.test_admin import commerce_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def checkout(mysql_app, user_factory, monkeypatch):
    uid, _ = user_factory()
    mysql_app.config["MOCK_PAYMENT_ENABLED"] = True
    monkeypatch.setattr(
        commerce,
        "runtime_commerce",
        lambda: (CommerceSettings.model_validate(commerce_settings()), None),
    )
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
            select(func.count()).select_from(CreditEntry).where(CreditEntry.source_order_id == paid.id)
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
