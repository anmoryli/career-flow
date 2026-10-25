"""Mock checkout and membership entitlements, serialized per user in MySQL."""

from datetime import timedelta

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import CommerceOrder, CreditEntry, Membership, MembershipCycle, utcnow
from app.services import credits
from app.services.admin_config import runtime_commerce
from app.services.errors import BusinessError

PERIODS = {"membership_30": 30, "membership_90": 90, "membership_365": 365}
PACKS = {"credit_pack_1", "credit_pack_2", "credit_pack_3"}


def mock_enabled():
    return (
        current_app.config["APP_ENV"] != "production" and current_app.config["MOCK_PAYMENT_ENABLED"]
    )


def create_order(user_id, request_key, plan_code):
    if not mock_enabled():
        raise BusinessError("模拟支付未开放。", 403)
    if plan_code not in PERIODS and plan_code not in PACKS:
        raise BusinessError("请选择有效套餐。", 422)
    credits.owner_lock(user_id)
    existing = db.session.scalar(
        select(CommerceOrder)
        .where(CommerceOrder.user_id == user_id, CommerceOrder.request_key == str(request_key))
        .with_for_update()
    )
    if existing:
        if existing.plan_code != plan_code:
            raise BusinessError("同一请求不能更换套餐。", 409)
        db.session.commit()
        return existing
    settings, revision_id = runtime_commerce()
    if settings is None:
        raise BusinessError("管理员尚未开放套餐。", 503)
    offer = getattr(settings, plan_code)
    item = CommerceOrder(
        user_id=user_id,
        request_key=str(request_key),
        kind="membership" if plan_code in PERIODS else "credits",
        plan_code=plan_code,
        price_yuan=offer.price_yuan,
        credits=offer.credits,
        period_days=PERIODS.get(plan_code, 0),
        state="pending",
        config_revision_id=revision_id,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _issue_membership(order):
    now = utcnow()
    membership = db.session.get(Membership, order.user_id, with_for_update=True)
    start = max(now, membership.expires_at) if membership else now
    end = start + timedelta(days=order.period_days)
    if membership is None:
        membership = Membership(user_id=order.user_id, expires_at=end, next_grant_at=start)
        db.session.add(membership)
        db.session.flush()
    else:
        membership.expires_at = end
    for offset in range(0, order.period_days, 30):
        cycle_start = start + timedelta(days=offset)
        cycle = MembershipCycle(
            user_id=order.user_id,
            order_id=order.id,
            starts_at=cycle_start,
            ends_at=min(cycle_start + timedelta(days=30), end),
            credits=order.credits,
        )
        db.session.add(cycle)
        db.session.flush()
        if cycle_start <= now:
            credits.grant(order.user_id, cycle.credits, "member", cycle_id=cycle.id)
    membership.next_grant_at = _next_grant_at(order.user_id, end)


def _next_grant_at(user_id, expiry):
    pending = db.session.scalar(
        select(MembershipCycle.starts_at)
        .outerjoin(CreditEntry, CreditEntry.source_cycle_id == MembershipCycle.id)
        .where(
            MembershipCycle.user_id == user_id,
            MembershipCycle.ends_at > utcnow(),
            CreditEntry.id.is_(None),
        )
        .order_by(MembershipCycle.starts_at)
        .limit(1)
    )
    return pending or expiry


def grant_due(user_id):
    """Issue scheduled cycles when a user returns; repeated calls cannot duplicate grants."""
    credits.owner_lock(user_id)
    membership = db.session.get(Membership, user_id, with_for_update=True)
    if membership is None or membership.next_grant_at > utcnow():
        return 0
    now = utcnow()
    due = db.session.scalars(
        select(MembershipCycle)
        .outerjoin(CreditEntry, CreditEntry.source_cycle_id == MembershipCycle.id)
        .where(
            MembershipCycle.user_id == user_id,
            MembershipCycle.starts_at <= now,
            MembershipCycle.ends_at > now,
            CreditEntry.id.is_(None),
        )
        .order_by(MembershipCycle.starts_at)
    ).all()
    for cycle in due:
        credits.grant(user_id, cycle.credits, "member", cycle_id=cycle.id)
    db.session.flush()
    membership.next_grant_at = _next_grant_at(user_id, membership.expires_at)
    return len(due)


def settle_mock(user_id, order_id, outcome):
    if not mock_enabled():
        raise BusinessError("模拟支付未开放。", 403)
    if outcome not in {"success", "failure"}:
        raise BusinessError("请选择模拟成功或失败。", 422)
    credits.owner_lock(user_id)
    order = db.session.scalar(
        select(CommerceOrder)
        .where(CommerceOrder.id == order_id, CommerceOrder.user_id == user_id)
        .with_for_update()
    )
    if order is None:
        raise BusinessError("订单不存在。", 404)
    target = "paid" if outcome == "success" else "failed"
    if order.state != "pending":
        if order.state != target:
            raise BusinessError("订单已经完成，不能更改支付结果。", 409)
        db.session.commit()
        return order
    if outcome == "success":
        if order.kind == "credits":
            credits.grant(user_id, order.credits, "purchased", order_id=order.id)
        else:
            _issue_membership(order)
    order.state = target
    order.completed_at = utcnow()
    db.session.commit()
    return order
