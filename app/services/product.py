"""Product quotas, privacy-limited events and auditable model usage (not points)."""

from decimal import Decimal

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert

from app.extensions import db
from app.models import (
    AIOperation,
    ModelCallUsage,
    ProductEvent,
    ResumeExportGrant,
    ResumeVersion,
    utcnow,
)
from app.product_schemas import ProductPolicy
from app.services.errors import BusinessError

EVENTS = {
    "resume_created",
    "resume_completed",
    "resume_saved",
    "ai_adopted",
    "ai_edited_after_adoption",
    "diagnosis_started",
    "diagnosis_completed",
    "report_completed",
    "job_version_saved",
    "membership_activated",
    "pdf_exported",
    "share_created",
    "share_revoked",
    "invitation_registered",
    "model_call",
}
PROPERTIES = {
    "resume_id",
    "version_id",
    "revision",
    "operation_id",
    "diagnostic_id",
    "parent_id",
    "plan_code",
    "payment_mode",
    "model_id",
    "attempt",
    "tokens",
    "input_tokens",
    "output_tokens",
    "policy_revision_id",
    "input_rate",
    "output_rate",
    "outcome",
    "share_id",
    "inviter_id",
    "path",
    "amount_minor",
    "starts_at",
    "ends_at",
    "period_days",
}


def record_event(user_id, name, key, **properties):
    if name not in EVENTS or set(properties) - PROPERTIES:
        raise ValueError("Unregistered product event or property")
    if any(not isinstance(value, (str, int, bool, type(None))) for value in properties.values()):
        raise ValueError("Only bounded scalar event properties are supported")
    if any(isinstance(value, str) and len(value) > 160 for value in properties.values()):
        raise ValueError("Event properties must not contain document text")
    statement = insert(ProductEvent).values(
        user_id=user_id,
        name=name,
        event_key=str(key)[:120],
        properties=properties,
        created_at=utcnow(),
    )
    db.session.execute(statement.on_duplicate_key_update(id=ProductEvent.id))


def policy():
    from app.services.admin_config import active_revision

    revision = active_revision("product")
    values = (
        revision.settings
        if revision and revision.settings.get("enabled", True)
        else current_app.config.get("PRODUCT_POLICY", {})
    )
    return ProductPolicy.model_validate(values), revision.id if revision else None


def month_start(now=None):
    now = now or utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def monthly_usage(user_id, exclude=None, *, current=False):
    now = utcnow()
    statement = select(AIOperation).where(
        AIOperation.user_id == user_id, AIOperation.created_at >= month_start(now)
    )
    if current:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    items = db.session.scalars(statement).all()
    relevant = [item for item in items if item.id != exclude]

    def active(item):
        return item.state in {"queued", "running"} or (
            item.state == "quoted" and item.expires_at > now
        )

    counted = [
        item
        for item in relevant
        if item.kind == "analysis"
        and item.diagnostic_id
        and (item.state == "succeeded" or active(item))
    ]
    # Provider calls remain billable after a user cancels a running task.
    # Prefer actual per-attempt usage; legacy operations retain their aggregate.
    actual = (
        dict(
            db.session.execute(
                select(ModelCallUsage.operation_id, func.sum(ModelCallUsage.total_tokens))
                .where(
                    ModelCallUsage.user_id == user_id,
                    ModelCallUsage.operation_id.in_([item.id for item in relevant]),
                )
                .group_by(ModelCallUsage.operation_id)
            ).all()
        )
        if relevant
        else {}
    )
    return dict(
        tokens=sum(int(actual.get(item.id) or item.tokens or 0) for item in relevant),
        reserved=sum(
            item.input_snapshot.get("quota_reserved_tokens", 0) for item in relevant if active(item)
        ),
        diagnostic_ids={item.diagnostic_id for item in counted},
        free_analyses=len(counted),
    )


def quota_info(user_id):
    from app.services.commerce import membership_active

    config, _ = policy()
    usage = monthly_usage(user_id)
    paid = membership_active(user_id)
    limit = config.member_analyses_monthly if paid else config.free_analyses_monthly
    used = len(usage["diagnostic_ids"]) if paid else usage["free_analyses"]
    start = month_start()
    reset = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return dict(
        analysis_limit=limit,
        member_analysis_limit=config.member_analyses_monthly,
        free_analysis_limit=config.free_analyses_monthly,
        analysis_used=used,
        analysis_remaining=max(0, limit - used),
        tokens_used=usage["tokens"],
        tokens_reserved=usage["reserved"],
        soft_tokens=config.member_soft_tokens_monthly,
        hard_tokens=config.member_hard_tokens_monthly,
        light_model_configured=bool(config.light_model_id),
        budget_degraded=paid
        and usage["tokens"] + usage["reserved"] >= config.member_soft_tokens_monthly,
        quota_resets_at=reset,
    )


def ensure_full_access(user_id, operation=None):
    from app.services.commerce import membership_active

    if membership_active(user_id) or (
        operation is not None and operation.input_snapshot.get("access_tier", "member") == "member"
    ):
        return
    raise BusinessError(
        "已可查看匹配分数与缺口；开通会员后可逐段改写、补充追问和生成完整报告。", 403
    )


def full_access(user_id, operation):
    from app.services.commerce import membership_active

    return (
        membership_active(user_id)
        or operation.input_snapshot.get("access_tier", "member") == "member"
    )


def ensure_analysis(user_id, diagnostic_id=None, kind="analysis", exclude=None):
    from app.services.commerce import membership_active

    paid = membership_active(user_id)
    if kind == "report" and not paid:
        ensure_full_access(user_id)
    config, _ = policy()
    used = monthly_usage(user_id, exclude, current=True)
    count = len(used["diagnostic_ids"]) if paid else used["free_analyses"]
    if paid and diagnostic_id in used["diagnostic_ids"]:
        return
    if count >= (config.member_analyses_monthly if paid else config.free_analyses_monthly):
        raise BusinessError("本自然月的岗位匹配额度已用完，下月自动重置；已有结果仍可查看。", 403)


def prepare_snapshot(user_id, snapshot, exclude=None):
    from app.services.admin_config import runtime_model_profile
    from app.services.commerce import membership_active

    config, revision = policy()
    usage = monthly_usage(user_id, exclude, current=True)
    paid = membership_active(user_id)
    if snapshot.get("access_tier") == "member" and not paid:
        raise BusinessError("会员权益已变化，请重新开始本次操作。", 403)
    snapshot.setdefault("access_tier", "member" if paid else "free_preview")
    estimate = (
        max(1, len(str(snapshot)) * 2 + 6000)
        * 2
        * max(1, len(snapshot.get("model_candidates", [])))
    )
    if paid and usage["tokens"] + usage["reserved"] + estimate > config.member_hard_tokens_monthly:
        raise BusinessError("本月AI公平使用安全上限已达，仍可编辑、查看已有结果和导出。", 403)
    if (
        paid
        and usage["tokens"] + usage["reserved"] >= config.member_soft_tokens_monthly
        and not snapshot.get("budget_mode")
    ):
        if not config.light_model_id:
            raise BusinessError(
                "本月标准模型预算已用完，管理员尚未配置轻量模型；仍可编辑与导出。", 403
            )
        profile = runtime_model_profile(snapshot.get("model_revision_id"), config.light_model_id)
        if not profile.get("enabled") or not profile.get("secret"):
            raise BusinessError("轻量模型尚不可用，请联系管理员；本次未占用额度。", 503)
        snapshot["standard_model"] = snapshot["model"]
        snapshot["standard_model_candidates"] = snapshot.get(
            "model_candidates", [snapshot["model"]]
        )
        snapshot["model"] = config.light_model_id
        snapshot["model_candidates"] = [config.light_model_id]
        snapshot["budget_mode"] = "light"
    snapshot["quota_reserved_tokens"] = estimate
    snapshot["quota_policy_revision_id"] = revision
    return snapshot


def public_result(user_id, operation):
    if full_access(user_id, operation) or not operation.result:
        return operation.result
    return {
        key: value
        for key, value in operation.result.items()
        if key in {"summary", "dimensions", "overall_score", "findings"}
    }


def export_info(user_id):
    grant = db.session.get(ResumeExportGrant, user_id)
    version = (
        db.session.get(ResumeVersion, grant.version_id) if grant and grant.version_id else None
    )
    return dict(
        free_export_remaining=0 if grant else 1,
        free_export_resume_id=version.resume_id if version else None,
        free_export_revision=version.revision if version else None,
    )


def authorize_export(user_id, version, *, consume=False):
    from app.services.commerce import lock_user, membership_active

    lock_user(user_id)
    if not membership_active(user_id):
        grant = db.session.scalar(
            select(ResumeExportGrant)
            .where(ResumeExportGrant.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if grant and grant.version_id != version.id:
            raise BusinessError("一次免费PDF导出已使用；原版本可重复下载，其他版本需会员。", 403)
        if grant is None:
            if not consume:
                raise BusinessError("请先通过编辑器的“首次免费导出”领取本次PDF。", 403)
            db.session.add(ResumeExportGrant(user_id=user_id, version_id=version.id))
    if consume:
        record_event(
            user_id,
            "pdf_exported",
            f"export:{version.id}",
            resume_id=version.resume_id,
            version_id=version.id,
            revision=version.revision,
        )
    db.session.commit()


class TokenUsage(int):
    def __new__(cls, total, input_tokens=None, output_tokens=None):
        result = int.__new__(cls, total)
        result.input_tokens = input_tokens
        result.output_tokens = output_tokens
        return result

    @classmethod
    def from_usage(cls, usage):
        return cls(
            usage.input_tokens + usage.output_tokens, usage.input_tokens, usage.output_tokens
        )


def call_usage(attempt, model, usage, prices, outcome):
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total = int(usage) if isinstance(usage, int) and usage > 0 else None
    price = prices.model_prices.get(model)
    cost = (
        (
            (
                Decimal(input_tokens) * price.input_per_million_cny
                + Decimal(output_tokens) * price.output_per_million_cny
            )
            / Decimal(1000000)
        ).quantize(Decimal(".000001"))
        if price and input_tokens is not None and output_tokens is not None
        else None
    )
    return dict(
        attempt=attempt,
        model_id=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
        estimated_cost_cny=cost,
        outcome=outcome,
        input_rate=str(price.input_per_million_cny) if price else None,
        output_rate=str(price.output_per_million_cny) if price else None,
    )


def store_call_usage(operation, calls, revision):
    for call in calls:
        exists = db.session.scalar(
            select(ModelCallUsage.id).where(
                ModelCallUsage.operation_id == operation.id,
                ModelCallUsage.attempt == call["attempt"],
            )
        )
        if exists:
            continue
        db.session.add(
            ModelCallUsage(
                user_id=operation.user_id,
                operation_id=operation.id,
                **{
                    key: value
                    for key, value in call.items()
                    if key not in {"input_rate", "output_rate"}
                },
            )
        )
        record_event(
            operation.user_id,
            "model_call",
            f"model-call:{operation.id}:{call['attempt']}",
            operation_id=operation.id,
            model_id=call["model_id"],
            attempt=call["attempt"],
            tokens=call["total_tokens"],
            input_tokens=call["input_tokens"],
            output_tokens=call["output_tokens"],
            policy_revision_id=revision,
            input_rate=call.get("input_rate"),
            output_rate=call.get("output_rate"),
            outcome=call["outcome"],
        )
