from flask import Blueprint, abort, g, render_template, request
from sqlalchemy import select

from app.diagnosis_schemas import AnswerInput, ApplySuggestion, QuoteInput
from app.extensions import db
from app.models import AIOperation, Diagnostic, DiagnosticAnswer, JobTarget, Resume
from app.services import diagnosis, task_queue
from app.services.career import owned
from app.services.commerce import membership_active
from app.services.interactions import active_question
from app.services.model_runtime import diagnosis_job_seconds, public_ai_error
from app.web.routes import input_data, login_required

diagnosis_web = Blueprint("diagnosis", __name__)


def operation_json(item):
    from app.services.product import public_result
    return {
        "id": item.id,
        "state": item.state,
        "kind": item.kind,
        "charged": item.charged,
        "error": public_ai_error(item.error),
        "result": public_result(g.user.id,item),
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
            if item.state == "succeeded" and item.result
        ),
        None,
    )
    active_operation = next(
        (item for item in operations if item.state in {"queued", "running"}), None
    )
    latest_failed_operation = (
        operations[0]
        if operations
        and operations[0].kind in {"analysis", "report"}
        and operations[0].state == "failed"
        else None
    )
    active_job_rows = db.session.execute(
        select(AIOperation, Diagnostic, JobTarget)
        .join(Diagnostic, AIOperation.diagnostic_id == Diagnostic.id)
        .join(JobTarget, Diagnostic.job_id == JobTarget.id)
        .where(
            AIOperation.user_id == g.user.id,
            AIOperation.state.in_(["queued", "running"]),
        )
        .order_by(AIOperation.id.desc())
    ).all()
    active_jobs = []
    seen_active_job_ids = set()
    for row in active_job_rows:
        if row[2].id not in seen_active_job_ids:
            active_jobs.append(row)
            seen_active_job_ids.add(row[2].id)
    from app.services.product import full_access
    can_review=bool(suggestion_operation and full_access(g.user.id,suggestion_operation))
    if not can_review:
        suggestion_operation=None
    resume = db.session.get(Resume, job.resume_id)
    return render_template(
        "frontend/analysis/detail.html",
        job=job,
        can_review=can_review,
        may_run_deep=membership_active(g.user.id),
        diagnostic=diagnostic,
        operations=operations,
        answers=answers,
        latest_analysis=latest_analysis,
        latest_report=latest_report,
        suggestion_operation=suggestion_operation,
        active_operation=active_operation,
        latest_failed_operation=latest_failed_operation,
        active_jobs=active_jobs,
        resume=resume,
        configured=diagnosis.is_configured(),
        question_form=active_question(diagnostic.conversation_id),
        latest_note=next(
            (item.note for item in operations if item.state == "succeeded" and item.note), ""
        ),
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
    ):
        abort(404)
    resume = db.session.get(Resume, job.resume_id)
    from app.services.product import ensure_full_access
    ensure_full_access(g.user.id,operation)
    from app.services.diagnosis_review import review_paragraphs

    return render_template(
        "frontend/analysis/review.html",
        review_rows=review_paragraphs(operation),        job=job,
        diagnostic=diagnostic,
        operation=operation,
        resume=resume,
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
    return _dispatch(diagnosis.confirm(g.user.id, item.id))


@diagnosis_web.post("/api/operations/<int:item_id>/confirm")
@login_required
def confirm(item_id):
    return _dispatch(diagnosis.confirm(g.user.id, item_id))


def _dispatch(item):
    """Queue a confirmed analysis and announce the wait in the chat panel.

    The queue notice is published before the hand-off so it cannot land after
    the worker's first stage event and make the panel step backwards.
    """
    from app.services.diagnosis import STAGE_MESSAGES
    from app.services.operation_events import publish

    if item.state != "queued":
        return operation_json(item)
    publish(item.id, "stage", {"message": STAGE_MESSAGES["queued"], "kind": "analysis"})
    try:
        task_queue.enqueue("diagnosis", item.id, diagnosis_job_seconds(item.input_snapshot))
    except Exception:
        publish(item.id, "failed", {"message": "任务队列暂不可用，请重试。"})
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


@diagnosis_web.get("/api/operations/<int:item_id>/stream")
@login_required
def stream(item_id):
    """Server-Sent Events for one operation: stage, delta, result, done, failed."""
    import json

    from flask import Response, stream_with_context

    from app.services import operation_events

    operation_id = owned(AIOperation, g.user.id, item_id).id

    def events():
        # An SSE response can live for minutes; it must not pin a MySQL
        # connection for that long. Redis carries everything it needs.
        db.session.remove()
        yield "retry: 3000\n\n"
        for record in operation_events.subscribe(operation_id):
            if record is None:
                yield ": ping\n\n"
                continue
            payload = json.dumps(record["data"], ensure_ascii=False)
            yield f"id: {record['seq']}\nevent: {record['event']}\ndata: {payload}\n\n"

    response = Response(stream_with_context(events()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    # Reverse proxies must not buffer the stream into one late blob.
    response.headers["X-Accel-Buffering"] = "no"
    return response


@diagnosis_web.get("/api/operations/<int:item_id>/panel")
@login_required
def panel(item_id):
    """Server-rendered result panel, swapped in as soon as an analysis lands."""
    from app.services.product import full_access

    item = owned(AIOperation, g.user.id, item_id)
    if item.diagnostic_id is None:
        abort(404)
    diagnostic = owned(Diagnostic, g.user.id, item.diagnostic_id)
    job = owned(JobTarget, g.user.id, diagnostic.job_id)
    return render_template(
        "frontend/analysis/_panel.html",
        operation=item,
        job_id=job.id,
        can_review=bool(item.result and full_access(g.user.id, item)),
    )


@diagnosis_web.get("/api/diagnostics/<int:item_id>/chat")
@login_required
def chat(item_id):
    """Copilot thread and composer, re-rendered after a run finishes."""
    diagnostic = owned(Diagnostic, g.user.id, item_id)
    return render_template(
        "frontend/analysis/_copilot.html", **copilot_context(g.user.id, diagnostic)
    )


def copilot_context(user_id, diagnostic):
    """Shared context for the conversation column, used on paint and refresh."""
    from app.services.product import full_access

    job = owned(JobTarget, user_id, diagnostic.job_id)
    resume = db.session.get(Resume, job.resume_id)
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
    suggestion_operation = next(
        (item for item in operations if item.state == "succeeded" and item.result), None
    )
    return {
        "job": job,
        "resume": resume,
        "answers": answers,
        "diagnostic": diagnostic,
        "operations": operations,
        "active_operation": next(
            (item for item in operations if item.state in {"queued", "running"}), None
        ),
        "suggestion_operation": suggestion_operation,
        "can_review": bool(suggestion_operation and full_access(user_id, suggestion_operation)),
        "question_form": active_question(diagnostic.conversation_id),
        "configured": diagnosis.is_configured(),
        # The newest recap already persisted; a reload replays it instead of
        # losing what the user just watched arrive.
        "latest_note": next(
            (item.note for item in operations if item.state == "succeeded" and item.note), ""
        ),
    }


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
