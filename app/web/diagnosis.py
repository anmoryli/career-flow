from flask import Blueprint, current_app, g, render_template
from rq import Queue
from sqlalchemy import select

from app.diagnosis_schemas import AnswerInput, ApplySuggestion, QuoteInput
from app.extensions import db
from app.models import AIOperation, CreditEntry, DiagnosticAnswer, JobTarget
from app.services import diagnosis
from app.services.career import owned
from app.services.interactions import active_question
from app.web.routes import input_data, login_required

diagnosis_web = Blueprint("diagnosis", __name__)


def operation_json(item):
    return {
        "id": item.id,
        "state": item.state,
        "kind": item.kind,
        "ceiling": item.ceiling,
        "charged": item.charged,
        "error": item.error,
        "result": item.result,
        "attempts": item.attempts,
    }


@diagnosis_web.get("/jobs/<int:job_id>")
@login_required
def detail(job_id):
    job = owned(JobTarget, g.user.id, job_id)
    diagnostic = diagnosis.get_diagnostic(g.user.id, job.id)
    operations = db.session.scalars(
        select(AIOperation)
        .where(AIOperation.diagnostic_id == diagnostic.id)
        .order_by(AIOperation.id.desc())
        .limit(100)
    ).all()
    answers = db.session.scalars(
        select(DiagnosticAnswer)
        .where(DiagnosticAnswer.diagnostic_id == diagnostic.id)
        .order_by(DiagnosticAnswer.round)
    ).all()
    return render_template(
        "diagnosis.html",
        job=job,
        diagnostic=diagnostic,
        operations=operations,
        answers=answers,
        balance=diagnosis.account(g.user.id),
        configured=diagnosis.is_configured(),
        question_form=active_question(diagnostic.conversation_id),
    )


@diagnosis_web.post("/api/diagnostics/<int:item_id>/quote")
@login_required
def quote(item_id):
    return operation_json(
        diagnosis.quote(g.user.id, item_id, QuoteInput.model_validate(input_data()))
    )


@diagnosis_web.post("/api/operations/<int:item_id>/confirm")
@login_required
def confirm(item_id):
    item = diagnosis.confirm(g.user.id, item_id)
    if item.state == "queued":
        try:
            Queue("careerflow", connection=current_app.extensions["redis"]).enqueue(
                "app.jobs.diagnosis_job",
                item.id,
                job_timeout=120,
                job_id=f"diagnosis-{item.id}",
            )
        except Exception:
            diagnosis.cancel(g.user.id, item.id)
            return {"error": "任务队列暂不可用，冻结积分已释放，请重新预估。"}, 503
    return operation_json(item)


@diagnosis_web.post("/api/operations/<int:item_id>/cancel")
@login_required
def cancel(item_id):
    return operation_json(diagnosis.cancel(g.user.id, item_id))


@diagnosis_web.get("/api/operations/<int:item_id>")
@login_required
def operation(item_id):
    return operation_json(owned(AIOperation, g.user.id, item_id))


@diagnosis_web.post("/api/diagnostics/<int:item_id>/answer")
@login_required
def answer(item_id):
    item = diagnosis.answer(g.user.id, item_id, AnswerInput.model_validate(input_data()))
    return {"rounds": item.rounds, "revision": item.revision}


@diagnosis_web.post("/api/operations/<int:item_id>/apply")
@login_required
def apply(item_id):
    return diagnosis.apply_suggestions(
        g.user.id, item_id, ApplySuggestion.model_validate(input_data())
    ), 201


@diagnosis_web.get("/api/credits")
@login_required
def credits():
    from app.services.commerce import grant_due

    grant_due(g.user.id)
    balance = diagnosis.account(g.user.id)
    entries = db.session.scalars(
        select(CreditEntry)
        .where(CreditEntry.user_id == g.user.id)
        .order_by(CreditEntry.id.desc())
        .limit(100)
    ).all()
    db.session.commit()
    return {
        "available": balance.available,
        "frozen": balance.frozen,
        "entries": [
            {"kind": e.kind, "available_delta": e.available_delta, "frozen_delta": e.frozen_delta}
            for e in entries
        ],
    }
