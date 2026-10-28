from flask import Blueprint, current_app, g, render_template, request
from rq import Queue
from sqlalchemy import delete, select

from app.career_schemas import ConfirmDelete, CopyResume, JobSave, ResumeSave
from app.extensions import db
from app.models import AIOperation, JobTarget, Resume, ResumeVersion
from app.resume_ai_schemas import ResumeAIQuote, ResumeComposeQuote
from app.services import career, commerce, resume_ai
from app.services.errors import BusinessError
from app.web.routes import input_data, login_required

career_web = Blueprint("career", __name__)


@career_web.post("/api/resumes")
@login_required
def create_resume():
    return career.save_resume(g.user.id, ResumeSave.model_validate(input_data())), 201


@career_web.get("/api/resumes/<int:item_id>")
@login_required
def get_resume(item_id):
    item = career.owned(Resume, g.user.id, item_id)
    return career.serialize_resume(item)


@career_web.post("/api/resumes/<int:item_id>")
@login_required
def update_resume(item_id):
    return career.save_resume(g.user.id, ResumeSave.model_validate(input_data()), item_id)


@career_web.post("/api/resumes/<int:item_id>/copy")
@login_required
def copy_resume(item_id):
    return career.copy_resume(g.user.id, item_id, CopyResume.model_validate(input_data())), 201


@career_web.get("/api/resumes/<int:item_id>/versions")
@login_required
def versions(item_id):
    item = career.owned(Resume, g.user.id, item_id)
    rows = db.session.scalars(
        select(ResumeVersion)
        .where(ResumeVersion.resume_id == item.id)
        .order_by(ResumeVersion.revision.desc())
        .limit(100)
    ).all()
    return {"versions": [career.serialize_resume(item, version) for version in rows]}


@career_web.post("/api/resumes/<int:item_id>/delete")
@login_required
def delete_resume(item_id):
    from app.services.diagnosis import owner_lock

    ConfirmDelete.model_validate(input_data())
    owner_lock(g.user.id)
    item = career.owned(Resume, g.user.id, item_id, True)
    linked = db.session.scalar(
        select(JobTarget.id)
        .join(ResumeVersion, JobTarget.resume_version_id == ResumeVersion.id)
        .where(ResumeVersion.resume_id == item.id)
        .limit(1)
    )
    if linked:
        raise BusinessError("这份简历已关联岗位，请先删除对应岗位再删除简历。", 409)
    if db.session.scalar(
        select(AIOperation.id)
        .where(AIOperation.resume_id == item.id, AIOperation.state != "quoted")
        .limit(1)
    ):
        raise BusinessError("这份简历已有 AI 操作记录，不能单独删除。", 409)
    db.session.execute(delete(Resume).where(Resume.id == item.id))
    db.session.commit()
    return {"deleted": True}


@career_web.post("/api/jobs")
@login_required
def create_job():
    return career.save_job(g.user.id, JobSave.model_validate(input_data())), 201


@career_web.get("/api/jobs/<int:item_id>")
@login_required
def get_job(item_id):
    item = career.owned(JobTarget, g.user.id, item_id)
    version = db.session.get(ResumeVersion, item.resume_version_id)
    resume = career.owned(Resume, g.user.id, version.resume_id)
    return {
        "id": item.id,
        "title": item.title,
        "company": item.company,
        "description": item.description,
        "url": item.url,
        "is_saved": item.is_saved,
        "resume_id": resume.id,
        "resume_revision": version.revision,
    }


@career_web.post("/api/jobs/<int:item_id>/delete")
@login_required
def delete_job(item_id):
    from app.models import Diagnostic
    from app.services.diagnosis import owner_lock

    ConfirmDelete.model_validate(input_data())
    owner_lock(g.user.id)
    item = career.owned(JobTarget, g.user.id, item_id, True)
    if db.session.scalar(select(Diagnostic.id).where(Diagnostic.job_id == item.id)):
        raise BusinessError("此岗位已关联诊断及账务记录，不能单独删除。", 409)
    db.session.delete(item)
    db.session.commit()
    return {"deleted": True}


@career_web.get("/resumes/<int:item_id>/print")
@login_required
def print_resume(item_id):
    item = career.owned(Resume, g.user.id, item_id)
    commerce.ensure_resume_export_capacity(g.user.id)
    version = career.version_of(item, request.args.get("revision", type=int))
    return render_template("resume/print.html", resume=item, version=version)


def resume_operation_json(item):
    partial = (
        item.result.get("partial")
        if item.state == "running" and isinstance(item.result, dict)
        else None
    )
    return {
        "id": item.id,
        "state": item.state,
        "charged": item.charged,
        "result": None if partial else item.result,
        "partial": partial,
        "error": item.error,
        "expires_at": item.expires_at.isoformat() + "Z",
    }


@career_web.post("/api/resumes/<int:item_id>/ai/quote")
@login_required
def quote_resume_ai(item_id):
    item = resume_ai.quote(g.user.id, item_id, ResumeAIQuote.model_validate(input_data()))
    return resume_operation_json(item)


@career_web.post("/api/resumes/<int:item_id>/ai/compose/quote")
@login_required
def quote_resume_compose(item_id):
    from app.services.infrastructure import rate_limit

    rate_limit("resume-compose", str(g.user.id), 5, 60)
    item = resume_ai.quote_compose(
        g.user.id, item_id, ResumeComposeQuote.model_validate(input_data())
    )
    return resume_operation_json(item)


def queue_resume_operation(item):
    if item.state == "queued":
        try:
            Queue("careerflow", connection=current_app.extensions["redis"]).enqueue(
                "app.jobs.resume_ai_job",
                item.id,
                job_timeout=120,
                job_id=f"resume-ai-{item.id}",
            )
        except Exception:
            from app.services.diagnosis import cancel

            cancel(g.user.id, item.id)
            return None
    return item


@career_web.post("/api/resumes/<int:item_id>/ai/start")
@login_required
def start_resume_ai(item_id):
    item = resume_ai.quote(g.user.id, item_id, ResumeAIQuote.model_validate(input_data()))
    item = resume_ai.confirm(g.user.id, item.id)
    item = queue_resume_operation(item)
    if item is None:
        return {"error": "任务队列暂不可用，请重试。"}, 503
    return resume_operation_json(item)


@career_web.post("/api/resumes/<int:item_id>/ai/compose/start")
@login_required
def start_resume_compose(item_id):
    from app.services.infrastructure import rate_limit

    rate_limit("resume-compose", str(g.user.id), 5, 60)
    item = resume_ai.quote_compose(
        g.user.id, item_id, ResumeComposeQuote.model_validate(input_data())
    )
    item = resume_ai.confirm(g.user.id, item.id)
    item = queue_resume_operation(item)
    if item is None:
        return {"error": "任务队列暂不可用，请重试。"}, 503
    return resume_operation_json(item)


@career_web.post("/api/resume-ai/<int:item_id>/confirm")
@login_required
def confirm_resume_ai(item_id):
    item = resume_ai.confirm(g.user.id, item_id)
    if item.state == "queued":
        try:
            Queue("careerflow", connection=current_app.extensions["redis"]).enqueue(
                "app.jobs.resume_ai_job",
                item.id,
                job_timeout=120,
                job_id=f"resume-ai-{item.id}",
            )
        except Exception:
            from app.services.diagnosis import cancel

            cancel(g.user.id, item.id)
            return {"error": "任务队列暂不可用，请重试。"}, 503
    return resume_operation_json(item)


@career_web.get("/api/resume-ai/<int:item_id>")
@login_required
def resume_ai_status(item_id):
    item = career.owned(AIOperation, g.user.id, item_id)
    if item.resume_id is None:
        raise BusinessError("任务类型不匹配。", 404)
    return resume_operation_json(item)
