import hashlib
import io
import re

from sqlalchemy import select

from app.career_schemas import ResumeDocument
from app.extensions import db
from app.models import ResumeImport
from app.services.career import owned
from app.services.diagnosis import owner_lock
from app.services.errors import BusinessError


class PDFInputError(ValueError):
    pass


def create_import(user_id, request_key, content):
    if not content.startswith(b"%PDF-"):
        raise BusinessError("请选择有效 PDF 文件。", 422)
    if len(content) > 4 * 1024 * 1024:
        raise BusinessError("PDF 不能超过 4 MB。", 413)
    owner_lock(user_id)
    digest = hashlib.sha256(content).hexdigest()
    item = db.session.scalar(
        select(ResumeImport)
        .where(ResumeImport.user_id == user_id, ResumeImport.request_key == str(request_key))
        .with_for_update()
    )
    if item:
        if item.digest != digest:
            raise BusinessError("重复导入请求内容不一致。", 409)
    else:
        item = ResumeImport(
            user_id=user_id,
            request_key=str(request_key),
            digest=digest,
            content=content,
            state="queued",
        )
        db.session.add(item)
    db.session.commit()
    return item


def parse_pdf(content):
    import pdfplumber

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) > 20:
            raise PDFInputError("PDF 页数不能超过 20 页")
        lines = []
        for page in pdf.pages:
            lines.append((page.extract_text() or "")[:30000])
            if sum(map(len, lines)) > 100000:
                raise PDFInputError("PDF 文字过多")
        text = "\n".join(lines).strip()
    if not text:
        raise PDFInputError("未提取到文字，扫描件需要 OCR；请使用可复制文字的 PDF 或手动填写")
    email = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", text)
    phone = re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", text)
    document = ResumeDocument(
        email=email.group()[:120] if email else "", phone=phone.group() if phone else ""
    ).model_dump()
    return text, document


def run_import(item_id):
    item = db.session.get(ResumeImport, item_id)
    if not item:
        return
    owner_lock(item.user_id)
    item = owned(ResumeImport, item.user_id, item_id, True)
    if item.state != "queued":
        db.session.commit()
        return
    content = item.content
    item.state = "running"
    db.session.commit()
    try:
        text, document = parse_pdf(content)
        error = ""
    except Exception as exc:
        text, document = "", None
        error = (
            str(exc)
            if isinstance(exc, PDFInputError)
            else "PDF 无法解析，可能已加密或损坏。请使用未加密 PDF。"
        )
    owner_lock(item.user_id)
    item = owned(ResumeImport, item.user_id, item_id, True)
    if item.state != "running":
        return
    item.content = None  # Original binary is removed after processing, including failures.
    item.state = "failed" if error else "ready"
    item.error = error
    item.text = text
    item.document = document
    db.session.commit()
