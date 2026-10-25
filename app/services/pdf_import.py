import hashlib
import io
import math
import os
import re
import subprocess
import time

from sqlalchemy import select

from app.career_schemas import ResumeDocument
from app.extensions import db
from app.models import ResumeImport
from app.services.career import owned
from app.services.diagnosis import owner_lock
from app.services.errors import BusinessError


class PDFInputError(ValueError):
    pass


def ocr_page(page, deadline):
    """Render one textless page and recognize it without writing a user file to disk."""
    if page.width <= 0 or page.height <= 0 or page.width * page.height > 5_000_000:
        raise PDFInputError("扫描页尺寸过大，无法安全识别。")
    resolution = min(180, int(72 * math.sqrt(5_000_000 / (page.width * page.height))))
    image = page.to_image(resolution=resolution).original
    with io.BytesIO() as stream:
        image.save(stream, format="PNG")
        image_bytes = stream.getvalue()
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PDFInputError("扫描件识别超时，请减少页数或上传文字版 PDF。")
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "chi_sim+eng", "--psm", "3"],
            input=image_bytes,
            capture_output=True,
            timeout=min(20, remaining),
            check=False,
            env=os.environ | {"OMP_THREAD_LIMIT": "1"},
        )
    except FileNotFoundError:
        raise PDFInputError("OCR 服务未安装，请联系管理员或上传文字版 PDF。") from None
    except subprocess.TimeoutExpired:
        raise PDFInputError("扫描件识别超时，请减少页数或上传文字版 PDF。") from None
    if result.returncode:
        raise PDFInputError("扫描件识别失败，请检查 OCR 中文语言包或上传文字版 PDF。")
    return result.stdout.decode("utf-8", errors="replace").strip()


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

    deadline = time.monotonic() + 90
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) > 20:
            raise PDFInputError("PDF 页数不能超过 20 页")
        lines = []
        for page in pdf.pages:
            extracted = (page.extract_text() or "").strip()
            lines.append((extracted or ocr_page(page, deadline))[:30000])
            if sum(map(len, lines)) > 100000:
                raise PDFInputError("PDF 文字过多")
        text = "\n".join(lines).strip()
    if not text:
        raise PDFInputError("未识别出文字，请使用清晰扫描件、文字版 PDF 或手动填写。")
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
