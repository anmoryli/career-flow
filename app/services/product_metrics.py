"""Server-side value events and aggregate metrics without document contents."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import AIOperation, ModelCallUsage, ProductEvent, User, utcnow
from app.services.product import record_event


def resume_saved(user_id, resume, version):
    if version.revision == 1:
        record_event(user_id, "resume_created", f"resume-created:{resume.id}", resume_id=resume.id)
    record_event(
        user_id,
        "resume_saved",
        f"resume-saved:{version.id}",
        resume_id=resume.id,
        version_id=version.id,
        revision=version.revision,
    )
    doc = version.document
    if doc.get("name") and (
        doc.get("summary") or any(doc.get(key) for key in ("experiences", "projects", "education"))
    ):
        record_event(
            user_id,
            "resume_completed",
            f"resume-completed:{resume.id}",
            resume_id=resume.id,
            version_id=version.id,
        )
    from app.services.resume_ai import field_value

    operations = db.session.scalars(
        select(AIOperation).where(
            AIOperation.user_id == user_id,
            AIOperation.resume_id == resume.id,
            AIOperation.state == "succeeded",
        )
    ).all()
    adopted = db.session.scalars(
        select(ProductEvent).where(
            ProductEvent.user_id == user_id, ProductEvent.name == "ai_adopted"
        )
    ).all()
    for op in operations:
        if not op.result or "path" not in op.result or "proposed" not in op.result:
            continue
        try:
            value = field_value(doc, op.result["path"])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if value == op.result["proposed"]:
            record_event(
                user_id,
                "ai_adopted",
                f"ai-adopted:{op.id}",
                operation_id=op.id,
                resume_id=resume.id,
                version_id=version.id,
                path=op.result["path"],
            )
        elif any(event.properties.get("operation_id") == op.id for event in adopted):
            record_event(
                user_id,
                "ai_edited_after_adoption",
                f"ai-edited:{op.id}",
                operation_id=op.id,
                resume_id=resume.id,
                version_id=version.id,
            )


def metrics(days=30):
    from datetime import datetime

    now = utcnow()
    start = now - timedelta(days=days)
    events = db.session.scalars(select(ProductEvent).where(ProductEvent.created_at >= start)).all()

    def count(name):
        return sum(event.name == name for event in events)

    def users(name):
        return {event.user_id for event in events if event.name == name}

    def identifiers(name):
        return {
            event.properties.get("diagnostic_id")
            for event in events
            if event.name == name and event.properties.get("diagnostic_id") is not None
        }

    registered = {
        user.id for user in db.session.scalars(select(User).where(User.created_at >= start)).all()
    }
    weekly = set(
        db.session.scalars(
            select(ProductEvent.user_id)
            .where(
                ProductEvent.name == "job_version_saved",
                ProductEvent.created_at >= now - timedelta(days=7),
            )
            .distinct()
        ).all()
    )
    ops = db.session.scalars(select(AIOperation).where(AIOperation.created_at >= start)).all()
    rewrites = [op for op in ops if op.state == "succeeded" and op.resume_id is not None]
    calls = db.session.scalars(
        select(ModelCallUsage).where(ModelCallUsage.created_at >= start)
    ).all()
    known = sum((call.estimated_cost_cny or Decimal(0) for call in calls), Decimal(0))
    unknown = sum(call.estimated_cost_cny is None for call in calls)

    def ratio(a, b):
        return round(a / b, 4) if b else None

    live = [
        event
        for event in db.session.scalars(
            select(ProductEvent)
            .where(ProductEvent.name == "membership_activated")
            .order_by(ProductEvent.created_at)
        ).all()
        if event.properties.get("payment_mode") == "live"
    ]
    current_live = [event for event in live if event.created_at >= start]
    paid_users = {event.user_id for event in current_live}
    amounts = [event.properties.get("amount_minor") for event in current_live]
    revenue = (
        sum(amounts) / 100
        if amounts and all(isinstance(amount, int) and amount >= 0 for amount in amounts)
        else None
    )
    first = {}
    for event in live:
        first.setdefault(event.user_id, event)
    matured = [
        event
        for event in first.values()
        if now - timedelta(days=days + 30) <= event.created_at <= now - timedelta(days=30)
    ]
    retained = []
    for event in matured:
        spans = [other for other in live if other.user_id == event.user_id]
        try:
            retained.append(
                any(
                    datetime.fromisoformat(item.properties["starts_at"])
                    <= event.created_at + timedelta(days=30)
                    < datetime.fromisoformat(item.properties["ends_at"])
                    for item in spans
                )
            )
        except (KeyError, ValueError, TypeError):
            retained = []
            break
    member_calls = [call for call in calls if call.user_id in paid_users]
    member_unknown = any(call.estimated_cost_cny is None for call in member_calls)
    member_cost = sum((call.estimated_cost_cny or Decimal(0) for call in member_calls), Decimal(0))
    cost_ratio = float(member_cost) / revenue if revenue and not member_unknown else None
    started = identifiers("diagnosis_started")
    reported = identifiers("report_completed")
    saved = identifiers("job_version_saved")
    saved_resumes = {
        event.properties.get("resume_id") for event in events if event.name == "resume_saved"
    }
    return dict(
        window_days=days,
        weekly_job_version_users=len(weekly),
        registered_users=len(registered),
        first_resume_completion_rate=ratio(
            len(users("resume_completed") & registered), len(registered)
        ),
        saved_ai_adoption_rate=ratio(count("ai_adopted"), len(rewrites)),
        adoption_reedit_rate=ratio(count("ai_edited_after_adoption"), count("ai_adopted")),
        diagnosis_started=count("diagnosis_started"),
        diagnosis_completed=count("diagnosis_completed"),
        report_completed=count("report_completed"),
        job_version_saved=count("job_version_saved"),
        diagnosis_to_report_rate=ratio(len(started & reported), len(started)),
        report_to_version_rate=ratio(len(reported & saved), len(reported)),
        average_resume_save_rounds=ratio(count("resume_saved"), len(saved_resumes)),
        mock_membership_users=len(
            {
                event.user_id
                for event in events
                if event.name == "membership_activated"
                and event.properties.get("payment_mode") == "mock"
            }
        ),
        real_paid_users=len(paid_users),
        free_to_real_paid_rate=ratio(len(paid_users & registered), len(registered))
        if live
        else None,
        paid_first_month_retention=ratio(sum(retained), len(retained)),
        real_arpu_cny=revenue / len(paid_users) if revenue is not None and paid_users else None,
        known_estimated_model_cost_cny=str(known),
        unknown_cost_calls=unknown,
        ai_cost_per_real_member_cny=str(member_cost / len(paid_users))
        if paid_users and not member_unknown
        else None,
        ai_cost_to_arpu_ratio=cost_ratio,
        cost_health="alert_above_40_percent"
        if cost_ratio is not None and cost_ratio > 0.4
        else "within_threshold"
        if cost_ratio is not None
        else "unknown_revenue_or_model_cost",
        sample_status="模拟开通不计收入；成本为已配置单价与真实用量推算值，非供应商账单；缺少数据或分母为null。",
    )
