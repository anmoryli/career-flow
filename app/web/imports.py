from uuid import UUID

from flask import Blueprint, current_app, g, render_template, request
from rq import Queue

from app.career_schemas import CustomSection, ResumeDocument, ResumeSave
from app.extensions import db
from app.models import Resume, ResumeImport
from app.services.career import owned, save_resume, version_of
from app.services.pdf_import import create_import
from app.web.routes import input_data, login_required

imports_web = Blueprint("imports", __name__)


@imports_web.post("/api/guest/resume/parse")
def parse_guest_resume():
    """Extract a guest PDF in memory so login can be deferred until analysis."""
    from app.services.errors import BusinessError
    from app.services.infrastructure import rate_limit
    from app.services.pdf_import import PDFInputError, parse_pdf

    rate_limit("guest-pdf-import", request.remote_addr or "unknown", 3, 600)
    file = request.files.get("file")
    if file is None:
        raise BusinessError("请选择 PDF 简历。", 422)
    content = file.read(4 * 1024 * 1024 + 1)
    if len(content) > 4 * 1024 * 1024:
        raise BusinessError("PDF 不能超过 4 MB。", 413)
    if not content.startswith(b"%PDF-"):
        raise BusinessError("请选择有效 PDF 文件。", 422)
    try:
        text, document = parse_pdf(content)
    except PDFInputError as error:
        raise BusinessError(str(error), 422) from error
    return {"title": suggested_title(file.filename), "text": text, "document": document}


def suggested_title(filename: str) -> str:
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    title = "".join(char for char in name if char.isprintable() and char not in "/\\").strip()
    return title[:120] or "导入的简历"


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
                job_timeout=120,
                job_id=f"pdf-import-{item.id}",
            )
        except Exception:
            item.state = "failed"
            item.content = None
            item.error = "解析队列暂不可用，请稍后重新导入。"
            db.session.commit()
            return {"error": item.error}, 503
    return {"id": item.id, "state": item.state, "title": suggested_title(file.filename)}, 201


@imports_web.get("/imports/<int:item_id>")
@login_required
def detail(item_id):
    resume_id = request.args.get("resume_id", type=int)
    resume_revision = 0
    if resume_id:
        resume_revision = version_of(owned(Resume, g.user.id, resume_id)).revision
    return render_template(
        "frontend/resume/import_review.html",
        item=owned(ResumeImport, g.user.id, item_id),
        resume_id=resume_id,
        resume_revision=resume_revision,
        suggested_title=suggested_title(request.args.get("title", "")),
    )


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
    resume_id = data.pop("resume_id", None)
    resume_data = ResumeSave.model_validate(data)
    submitted_document = data.get("document")
    if not isinstance(submitted_document, dict):
        submitted_document = {}
    extracted_document = ResumeDocument.model_validate(item.document or {})
    extracted_document = extracted_document.model_copy(update={
        "name": submitted_document.get("name", extracted_document.name),
        "role": submitted_document.get("role", extracted_document.role),
        "phone": submitted_document.get("phone", extracted_document.phone),
        "email": submitted_document.get("email", extracted_document.email),
        "summary": submitted_document.get("summary", extracted_document.summary),
    })
    resume_data = resume_data.model_copy(update={"document": extracted_document})
    if resume_id:
        previous = version_of(owned(Resume, g.user.id, resume_id))
        custom_sections = [
            CustomSection.model_validate(section)
            for section in previous.document.get("custom_sections", [])
        ]
        custom_keys = [f"custom:{section.id}" for section in custom_sections]
        built_in = [
            "summary", "experiences", "projects", "education", "skills",
            "certificates", "languages",
        ]
        allowed = set(built_in) | set(custom_keys)
        section_order = [
            key for key in previous.document.get("section_order", built_in) if key in allowed
        ]
        section_order.extend(key for key in [*built_in, *custom_keys] if key not in section_order)
        hidden_sections = [
            key for key in previous.document.get("hidden_sections", []) if key in allowed
        ]
        imported_document = resume_data.document.model_copy(update={
            "custom_sections": custom_sections,
            "section_order": section_order,
            "hidden_sections": hidden_sections,
        })
        resume_data = resume_data.model_copy(update={"document": imported_document})
    return save_resume(g.user.id, resume_data, resume_id=resume_id), 200 if resume_id else 201
