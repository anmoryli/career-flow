from uuid import UUID

from flask import Blueprint, current_app, g, render_template, request
from rq import Queue

from app.career_schemas import ResumeSave
from app.extensions import db
from app.models import ResumeImport
from app.services.career import owned, save_resume
from app.services.pdf_import import create_import
from app.web.routes import input_data, login_required

imports_web = Blueprint("imports", __name__)


@imports_web.post("/api/imports")
@login_required
def upload():
    from app.services.infrastructure import rate_limit

    rate_limit("pdf-import", str(g.user.id), 10, 60)
    file = request.files.get("file")
    try:
        key = UUID(request.form.get("request_key", ""))
    except ValueError:
        return {"error": "导入请求编号无效。"}, 422
    if not file:
        return {"error": "请选择 PDF 文件。"}, 422
    item = create_import(g.user.id, key, file.read(4 * 1024 * 1024 + 1))
    if item.state == "queued":
        try:
            Queue("careerflow", connection=current_app.extensions["redis"]).enqueue(
                "app.jobs.pdf_import_job",
                item.id,
                job_timeout=60,
                job_id=f"pdf-import-{item.id}",
            )
        except Exception:
            item.state = "failed"
            item.content = None
            item.error = "解析队列暂不可用，请稍后重新导入。"
            db.session.commit()
            return {"error": item.error}, 503
    return {"id": item.id, "state": item.state}, 201


@imports_web.get("/imports/<int:item_id>")
@login_required
def detail(item_id):
    return render_template("import.html", item=owned(ResumeImport, g.user.id, item_id))


@imports_web.get("/api/imports/<int:item_id>")
@login_required
def status(item_id):
    item = owned(ResumeImport, g.user.id, item_id)
    return {"id": item.id, "state": item.state, "error": item.error}


@imports_web.post("/api/imports/<int:item_id>/confirm")
@login_required
def confirm(item_id):
    item = owned(ResumeImport, g.user.id, item_id)
    if item.state != "ready":
        return {"error": "解析尚未完成，不能确认。"}, 409
    data = input_data()
    if data.pop("confirmed", None) != "yes":
        return {"error": "请核对提取内容后确认。"}, 422
    return save_resume(g.user.id, ResumeSave.model_validate(data)), 201
