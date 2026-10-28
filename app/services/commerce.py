"""Membership plans and usage limits for the CareerFlow workspace."""

from datetime import timedelta
from decimal import Decimal

from flask import current_app
from sqlalchemy import func, select

from app.extensions import db
from app.models import AIOperation, CommerceOrder, Membership, Resume, User, utcnow
from app.services.errors import BusinessError

PLANS = {
    "membership_monthly": {"title": "月付会员", "price_yuan": Decimal("39.00"), "days": 30},
    "membership_quarterly": {"title": "季度会员", "price_yuan": Decimal("99.00"), "days": 90},
}
FREE_RESUME_LIMIT = 2
TOTAL_RESUME_LIMIT = 10
FREE_RESUME_AI_LIMIT = 5
RESUME_AI_KINDS = ("compose", "optimize", "expand", "generate", "professional", "concise")


def lock_user(user_id):
    db.session.scalar(select(User).where(User.id == user_id).with_for_update())


def mock_enabled():
    return current_app.config["APP_ENV"] in {"development", "testing"} and current_app.config[
        "MOCK_PAYMENT_ENABLED"
    ]


def membership_active(user_id):
    membership = db.session.get(Membership, user_id)
    return bool(membership and membership.expires_at > utcnow())


def entitlements(user_id):
    """Return current plan and usage without exposing legacy credit balances."""
    now = utcnow()
    membership = db.session.get(Membership, user_id)
    paid = bool(membership and membership.expires_at > now)
    resume_count = db.session.scalar(
        select(func.count()).select_from(Resume).where(Resume.user_id == user_id)
    )
    ai_used = db.session.scalar(
        select(func.count())
        .select_from(AIOperation)
        .where(
            AIOperation.user_id == user_id,
            AIOperation.resume_id.is_not(None),
            AIOperation.kind.in_(RESUME_AI_KINDS),
            (AIOperation.state == "succeeded")
            | (
                AIOperation.state.in_(("quoted", "queued", "running"))
                & (AIOperation.expires_at > now)
            ),
        )
    )
    plan_code = membership.plan_code if paid else "free"
    return {
        "plan_code": plan_code,
        "plan_name": PLANS.get(plan_code, {}).get("title", "免费版" if not paid else "会员"),
        "is_member": paid,
        "expires_at": membership.expires_at if paid else None,
        "resume_count": resume_count,
        "resume_limit": TOTAL_RESUME_LIMIT,
        "free_resume_limit": FREE_RESUME_LIMIT,
        "can_create_resume": resume_count < TOTAL_RESUME_LIMIT
        and (paid or resume_count < FREE_RESUME_LIMIT),
        "resume_ai_used": ai_used,
        "resume_ai_limit": None if paid else FREE_RESUME_AI_LIMIT,
        "resume_ai_remaining": None if paid else max(0, FREE_RESUME_AI_LIMIT - ai_used),
        "can_export_resume": paid,
    }


def ensure_resume_capacity(user_id):
    info = entitlements(user_id)
    if info["resume_count"] >= TOTAL_RESUME_LIMIT:
        raise BusinessError("每个账号最多保存 10 份简历。", 409)
    if not info["is_member"] and info["resume_count"] >= FREE_RESUME_LIMIT:
        raise BusinessError("免费版最多保存 2 份简历，开通会员后可保存更多。", 409)


def ensure_resume_ai_capacity(user_id):
    info = entitlements(user_id)
    if not info["is_member"] and info["resume_ai_remaining"] <= 0:
        raise BusinessError("免费版的 5 次简历 AI 优化额度已用完，开通会员可继续使用。", 403)


def ensure_job_analysis_capacity(user_id):
    if not membership_active(user_id):
        raise BusinessError("岗位分析暂不包含在免费版中，开通会员后即可使用。", 403)


def ensure_resume_export_capacity(user_id):
    if not membership_active(user_id):
        raise BusinessError("开通会员后即可导出简历 PDF。", 403)


def create_order(user_id, request_key, plan_code):
    if not mock_enabled():
        raise BusinessError("当前支付方式暂不可用。", 403)
    offer = PLANS.get(plan_code)
    if offer is None:
        raise BusinessError("请选择有效的会员方案。", 422)
    lock_user(user_id)
    existing = db.session.scalar(
        select(CommerceOrder)
        .where(CommerceOrder.user_id == user_id, CommerceOrder.request_key == str(request_key))
        .with_for_update()
    )
    if existing:
        if existing.plan_code != plan_code:
            raise BusinessError("同一请求不能更换方案。", 409)
        db.session.commit()
        return existing
    item = CommerceOrder(
        user_id=user_id,
        request_key=str(request_key),
        kind="membership",
        plan_code=plan_code,
        price_yuan=offer["price_yuan"],
        credits=0,
        period_days=offer["days"],
        state="pending",
        config_revision_id=None,
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
        membership = Membership(
            user_id=order.user_id,
            plan_code=order.plan_code,
            expires_at=end,
            next_grant_at=end,
        )
        db.session.add(membership)
    else:
        membership.plan_code = order.plan_code
        membership.expires_at = end
        membership.next_grant_at = end


def settle_mock(user_id, order_id, outcome):
    if not mock_enabled():
        raise BusinessError("模拟支付未开放。", 403)
    if outcome not in {"success", "failure"}:
        raise BusinessError("请选择有效的支付结果。", 422)
    lock_user(user_id)
    order = db.session.scalar(
        select(CommerceOrder)
        .where(CommerceOrder.id == order_id, CommerceOrder.user_id == user_id)
        .with_for_update()
    )
    if order is None:
        raise BusinessError("订单不存在。", 404)
    if order.kind != "membership" or order.plan_code not in PLANS:
        raise BusinessError("该订单不是当前可用的会员方案。", 409)
    target = "paid" if outcome == "success" else "failed"
    if order.state != "pending":
        if order.state != target:
            raise BusinessError("订单已经完成，不能更改支付结果。", 409)
        db.session.commit()
        return order
    if outcome == "success":
        _issue_membership(order)
    order.state = target
    order.completed_at = utcnow()
    db.session.commit()
    return order
