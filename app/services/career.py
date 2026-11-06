import base64
import binascii
import io
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.career_schemas import ResumeSave
from app.extensions import db
from app.models import AIOperation, JobTarget, Resume, User
from app.services.errors import BusinessError


def owned(model, user_id, item_id, lock=False):
    query = select(model).where(model.id == item_id, model.user_id == user_id)
    if lock:
        query = query.with_for_update()
    item = db.session.scalar(query.execution_options(populate_existing=True))
    if item is None:
        raise BusinessError("记录不存在或无权访问。", 404)
    return item


def serialize_resume(item):
    return {
        "id": item.id,
        "title": item.title,
        "revision": item.revision,
        "template": item.template,
        "document": item.document,
        "created_at": item.created_at.isoformat() + "Z",
        "parent_id": item.parent_id,
        "updated_at": item.updated_at.isoformat() + "Z",
    }


def validate_document(document):
    # Bound the complete document, including otherwise unbounded list strings.
    if len(json.dumps(document, ensure_ascii=False).encode()) > 4 * 1024 * 1024:
        raise BusinessError("简历内容过大。", 413)
    photo = document["photo"]
    if photo:
        try:
            prefix, content = photo.split(",", 1)
            raw = base64.b64decode(content, validate=True)
        except (ValueError, binascii.Error):
            raise BusinessError("照片格式无效。", 422) from None
        if len(raw) > 2.5 * 1024 * 1024:
            raise BusinessError("照片不能超过 2.5 MB。", 413)
        signatures = {
            "data:image/png;base64": raw.startswith(b"\x89PNG\r\n\x1a\n"),
            "data:image/jpeg;base64": raw.startswith(b"\xff\xd8\xff"),
            "data:image/webp;base64": raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
        }
        if not signatures.get(prefix):
            raise BusinessError("仅支持有效的 PNG、JPEG、WebP 照片。", 422)
        from PIL import Image

        try:
            with Image.open(io.BytesIO(raw)) as image:
                if not (96 <= image.width <= 4096 and 96 <= image.height <= 4096):
                    raise ValueError("dimensions")
                if image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("format")
                image.verify()
        except (OSError, ValueError, Image.DecompressionBombError):
            raise BusinessError("照片不能解码，或边长不在 96–4096 像素之间。", 422) from None


def save_resume(user_id, data, resume_id=None, parent_id=None, *, source_operation_id=None):
    document = data.document.model_dump()
    validate_document(document)
    key = str(data.request_key)
    try:
        # Serialize creates per owner, updates per resume. Same order for copies.
        db.session.scalar(select(User).where(User.id == user_id).with_for_update())
        item = (
            owned(Resume, user_id, resume_id, True)
            if resume_id
            else db.session.scalar(
                select(Resume)
                .where(Resume.user_id == user_id, Resume.request_key == key)
                .with_for_update()
            )
        )
        if item:
            if resume_id is None and item.parent_id != parent_id:
                raise BusinessError("复制来源与重复请求不一致。", 409)
            # A retried save (same request key) is idempotent; another save
            # since then must have bumped the revision and conflict.
            if item.last_save_key == key:
                if (
                    item.document != document
                    or item.title != data.title
                    or item.template != data.template
                ):
                    raise BusinessError("重复请求的内容不一致。", 409)
                result = serialize_resume(item)
                db.session.commit()
                return result
            if data.revision != item.revision:
                raise BusinessError("简历已在其他窗口更新，请先复制当前内容再重新载入。", 409)
        else:
            if data.revision:
                raise BusinessError("简历保存状态无效，请重新打开编辑器。", 409)
            from app.services.commerce import ensure_resume_capacity

            ensure_resume_capacity(user_id)
            item = Resume(
                user_id=user_id,
                request_key=key,
                title=data.title,
                template=data.template,
                document=document,
                revision=0,
                parent_id=parent_id,
            )
            db.session.add(item)
            db.session.flush()
        item.revision += 1
        item.title = data.title
        item.template = data.template
        item.document = document
        item.last_save_key = key
        db.session.flush()
        from app.services.product_metrics import resume_saved

        resume_saved(user_id, item)
        if source_operation_id is not None:
            from app.services.product import record_event

            operation = owned(AIOperation, user_id, source_operation_id)
            record_event(
                user_id,
                "job_version_saved",
                f"job-version:{item.id}",
                resume_id=item.id,
                parent_id=item.parent_id,
                operation_id=operation.id,
                diagnostic_id=operation.diagnostic_id,
                revision=item.revision,
            )
        db.session.commit()
        db.session.refresh(item)
        return serialize_resume(item)
    except IntegrityError:
        db.session.rollback()
        raise BusinessError("保存冲突，请重试。", 409) from None


def copy_resume(user_id, resume_id, data):
    original = owned(Resume, user_id, resume_id)
    return save_resume(
        user_id,
        ResumeSave(
            request_key=data.request_key,
            title=data.title,
            template=original.template,
            document=original.document,
        ),
        parent_id=original.id,
    )


def save_job(user_id, data):
    db.session.scalar(select(User).where(User.id == user_id).with_for_update())
    resume = owned(Resume, user_id, data.resume_id, True)
    if resume.revision != data.resume_revision:
        raise BusinessError("简历已更新，请刷新后重新创建岗位。", 409)
    if data.url and not data.url.startswith(("https://", "http://")):
        raise BusinessError("来源链接必须以 http:// 或 https:// 开头。", 422)
    values = {
        "title": data.title,
        "company": data.company,
        "description": data.description,
        "url": data.url,
        "resume_id": resume.id,
        "resume_revision": resume.revision,
        "is_saved": data.save_for_later,
    }
    item = db.session.scalar(
        select(JobTarget)
        .where(JobTarget.user_id == user_id, JobTarget.request_key == str(data.request_key))
        .with_for_update()
    )
    if item:
        if any(getattr(item, key) != value for key, value in values.items()):
            raise BusinessError("重复请求的岗位内容不一致。", 409)
    else:
        item = JobTarget(user_id=user_id, request_key=str(data.request_key), **values)
        db.session.add(item)
    db.session.commit()
    return {"id": item.id, **values}
