from flask import Blueprint, g, render_template, request
from sqlalchemy import delete, select

from app.career_schemas import ConfirmDelete, CopyResume, JobSave, ResumeSave
from app.extensions import db
from app.models import JobTarget, Resume, ResumeVersion
from app.services import career
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
    db.session.execute(delete(Resume).where(Resume.id == item.id))
    db.session.commit()
    return {"deleted": True}


@career_web.post("/api/jobs")
@login_required
def create_job():
    return career.save_job(g.user.id, JobSave.model_validate(input_data())), 201


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
    version = career.version_of(item, request.args.get("revision", type=int))
    return render_template("resume/print.html", resume=item, version=version)
