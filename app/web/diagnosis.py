from flask import Blueprint, abort, current_app, g, render_template, request
from rq import Queue
from sqlalchemy import select

from app.diagnosis_schemas import AnswerInput, ApplySuggestion, QuoteInput
from app.extensions import db
from app.models import AIOperation, DiagnosticAnswer, JobTarget, Resume, ResumeVersion
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
    latest_analysis = next(
        (item for item in operations if item.kind == "analysis" and item.state == "succeeded"),
        None,
    )
    latest_report = next(
        (item for item in operations if item.kind == "report" and item.state == "succeeded"),
        None,
    )
    suggestion_operation = next(
        (
            item
            for item in operations
            if item.state == "succeeded" and (item.result or {}).get("suggestions")
        ),
        None,
    )
    active_operation = next(
        (item for item in operations if item.state in {"queued", "running"}), None
    )
    resume_version = db.session.get(ResumeVersion, job.resume_version_id)
    resume = db.session.get(Resume, resume_version.resume_id) if resume_version else None
    return render_template(
        "diagnosis.html",
        job=job,
        diagnostic=diagnostic,
        operations=operations,
        answers=answers,
        latest_analysis=latest_analysis,
        latest_report=latest_report,
        suggestion_operation=suggestion_operation,
        active_operation=active_operation,
        resume=resume,
        resume_version=resume_version,
        configured=diagnosis.is_configured(),
        question_form=active_question(diagnostic.conversation_id),
    )


@diagnosis_web.get("/jobs/<int:job_id>/suggestions")
@login_required
def suggestions(job_id):
    job = owned(JobTarget, g.user.id, job_id)
    diagnostic = diagnosis.get_diagnostic(g.user.id, job.id)
    operation_id = request.args.get("operation_id", type=int)
    if operation_id is None:
        abort(404)
    operation = owned(AIOperation, g.user.id, operation_id)
    if (
        operation.diagnostic_id != diagnostic.id
        or operation.state != "succeeded"
        or not (operation.result or {}).get("suggestions")
    ):
        abort(404)
    resume_version = db.session.get(ResumeVersion, job.resume_version_id)
    resume = db.session.get(Resume, resume_version.resume_id) if resume_version else None
    return render_template(
        "diagnosis_suggestions.html",
        job=job,
        diagnostic=diagnostic,
        operation=operation,
        resume=resume,
        resume_version=resume_version,
    )


@diagnosis_web.post("/api/diagnostics/<int:item_id>/quote")
@login_required
def quote(item_id):
    return operation_json(
        diagnosis.quote(g.user.id, item_id, QuoteInput.model_validate(input_data()))
    )


@diagnosis_web.post("/api/diagnostics/<int:item_id>/start")
@login_required
def start(item_id):
    item = diagnosis.quote(g.user.id, item_id, QuoteInput.model_validate(input_data()))
    item = diagnosis.confirm(g.user.id, item.id)
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
            return {"error": "任务队列暂不可用，请重试。"}, 503
    return operation_json(item)


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
            return {"error": "任务队列暂不可用，请重试。"}, 503
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
