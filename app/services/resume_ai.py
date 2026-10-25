"""Billed, user-reviewed suggestions for one resume text field."""

import copy
import json
import math
import re
from datetime import timedelta

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import AIOperation, Resume, utcnow
from app.resume_ai_schemas import ResumeAIOutput
from app.services import credits
from app.services.career import owned, version_of
from app.services.diagnosis import is_configured, release
from app.services.errors import BusinessError

PROMPT_VERSION = "resume-rewrite-1"


def field_value(document, path):
    value = document
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def field_context(document, path):
    parts = path.split(".")
    if len(parts) == 1:
        return {"role": document.get("role", ""), "skills": document.get("skills", [])}
    entry = document[parts[0]][int(parts[1])]
    return {key: value for key, value in entry.items() if key != parts[-1] and key != "bullets"}


def quote(user_id, resume_id, data):
    credits.owner_lock(user_id)
    resume = owned(Resume, user_id, resume_id, True)
    previous = db.session.scalar(
        select(AIOperation)
        .where(AIOperation.user_id == user_id, AIOperation.request_key == str(data.request_key))
        .with_for_update()
    )
    if previous:
        snapshot = previous.input_snapshot
        if (
            previous.resume_id,
            previous.kind,
            snapshot.get("path"),
            previous.diagnostic_revision,
        ) != (resume_id, data.mode, data.path, data.revision):
            raise BusinessError("重复请求内容不一致。", 409)
        db.session.commit()
        return previous
    if resume.revision != data.revision:
        raise BusinessError("简历已更新，请等待保存后重新尝试。", 409)
    if db.session.scalar(
        select(AIOperation.id)
        .where(AIOperation.resume_id == resume_id, AIOperation.state.in_(("queued", "running")))
        .limit(1)
    ):
        raise BusinessError("这份简历已有 AI 任务正在执行。", 409)
    if not is_configured():
        raise BusinessError("AI 服务尚未配置。", 503)
    version = version_of(resume)
    try:
        original = field_value(version.document, data.path)
        context = field_context(version.document, data.path)
    except (KeyError, IndexError, ValueError, TypeError):
        raise BusinessError("简历条目不存在，请刷新页面。", 422) from None
    if not isinstance(original, str):
        raise BusinessError("只能改写单条文字。", 422)
    if not original.strip() and (
        data.mode != "generate"
        or not any(isinstance(v, str) and v.strip() for v in context.values())
    ):
        raise BusinessError("请先填写真实内容或同一条目的背景信息。", 422)
    from app.services.admin_config import runtime_model, runtime_model_route

    model = runtime_model()
    route = runtime_model_route("resume_rewrite", model["model_id"])
    snapshot = {
        "path": data.path,
        "original": original,
        "context": context,
        "mode": data.mode,
        "prompt_version": PROMPT_VERSION,
        "model": route["model_id"],
        "model_revision_id": model["revision_id"],
        "model_route_revision_id": route["revision_id"],
        "tokens_per_credit": model["tokens_per_credit"],
    }
    size = len(json.dumps(snapshot, ensure_ascii=False).encode())
    if size > 12000:
        raise BusinessError("改写内容过长，请缩短后重试。", 422)
    ceiling = max(1, math.ceil(2 * (size + 2048) / snapshot["tokens_per_credit"]))
    item = AIOperation(
        user_id=user_id,
        resume_id=resume_id,
        diagnostic_revision=resume.revision,
        request_key=str(data.request_key),
        kind=data.mode,
        state="quoted",
        ceiling=ceiling,
        input_snapshot=snapshot,
        expires_at=utcnow() + timedelta(minutes=10),
    )
    db.session.add(item)
    db.session.commit()
    return item


def confirm(user_id, operation_id):
    credits.owner_lock(user_id)
    item = owned(AIOperation, user_id, operation_id, True)
    if item.resume_id is None:
        raise BusinessError("任务类型不匹配。", 404)
    if item.state != "quoted":
        db.session.commit()
        return item
    resume = owned(Resume, user_id, item.resume_id, True)
    if item.expires_at <= utcnow() or resume.revision != item.diagnostic_revision:
        raise BusinessError("费用预估已过期或简历已更新。", 409)
    from app.services.admin_config import runtime_model, runtime_model_route

    model = runtime_model()
    route = runtime_model_route("resume_rewrite", model["model_id"])
    if (
        not is_configured()
        or item.input_snapshot["model"] != route["model_id"]
        or item.input_snapshot["model_revision_id"] != model["revision_id"]
        or item.input_snapshot["model_route_revision_id"] != route["revision_id"]
    ):
        raise BusinessError("模型配置已变化，请重新预估。", 503)
    from app.services.commerce import grant_due

    grant_due(user_id)
    credits.freeze(user_id, item.id, item.ceiling)
    item.state = "queued"
    db.session.commit()
    return item


def run_operation(operation_id):
    record = db.session.get(AIOperation, operation_id)
    if record is None or record.resume_id is None:
        return
    user_id = record.user_id
    credits.owner_lock(user_id)
    item = owned(AIOperation, user_id, operation_id, True)
    if item.state != "queued":
        db.session.commit()
        return
    item.state = "running"
    item.started_at = utcnow()
    snapshot = copy.deepcopy(item.input_snapshot)
    revision = item.diagnostic_revision
    db.session.commit()
    result = None
    tokens = 0
    attempts = 0
    for attempt in range(2):
        attempts = attempt + 1
        try:
            from app.services.model_provider import generate_resume

            provider = (
                current_app.extensions.get("resume_provider") if current_app.testing else None
            )
            raw, usage = (provider or generate_resume)(snapshot)
            if not isinstance(usage, int) or not 0 < usage <= 2000000:
                raise ValueError("费用用量不可用")
            tokens += usage
            output = ResumeAIOutput.model_validate(raw)
            # The model result remains a suggestion until the user accepts it.
            path = snapshot["path"]
            limit = (
                160
                if path.startswith("education.")
                else 600
                if path == "summary"
                else 2000
                if path.startswith("projects.")
                else 3000
            )
            if len(output.proposed) > limit:
                raise ValueError("改写超过字段长度")
            source_numbers = set(
                re.findall(
                    r"\d+(?:[.,]\d+)?%?",
                    json.dumps(
                        {"original": snapshot["original"], "context": snapshot["context"]},
                        ensure_ascii=False,
                    ),
                )
            )
            proposed_numbers = set(re.findall(r"\d+(?:[.,]\d+)?%?", output.proposed))
            if not proposed_numbers.issubset(source_numbers):
                raise ValueError("改写新增了未经确认的数字")
            result = {
                "original": snapshot["original"],
                "proposed": output.proposed,
                "reason": output.reason,
                "path": snapshot["path"],
                "revision": revision,
            }
            break
        except Exception as error:
            current_app.logger.warning(
                "resume_ai_attempt_failed operation=%s type=%s", operation_id, type(error).__name__
            )
    credits.owner_lock(user_id)
    item = owned(AIOperation, user_id, operation_id, True)
    if item.state != "running":
        db.session.commit()
        return
    item.attempts = attempts
    item.tokens = tokens
    if result is None:
        release(item, "failed", "模型超时、输出无效或费用不可查询；冻结积分已全额释放。")
    else:
        charged = min(item.ceiling, math.ceil(tokens / snapshot["tokens_per_credit"]))
        credits.settle(user_id, item.id, item.ceiling, charged)
        item.result = result
        item.charged = charged
        item.state = "succeeded"
    db.session.commit()
