"""Billed, user-reviewed suggestions for one resume text field."""

import copy
import json
import re
from datetime import timedelta

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import AIOperation, Resume, utcnow
from app.resume_ai_schemas import ResumeAIOutput, ResumeComposeOutput
from app.services.career import owned, version_of
from app.services.commerce import lock_user
from app.services.diagnosis import is_configured, release
from app.services.errors import BusinessError

PROMPT_VERSION = "resume-rewrite-1"


def quote_compose(user_id, resume_id, data):
    lock_user(user_id)
    resume = owned(Resume, user_id, resume_id, True)
    previous = db.session.scalar(
        select(AIOperation)
        .where(AIOperation.user_id == user_id, AIOperation.request_key == str(data.request_key))
        .with_for_update()
    )
    if previous:
        if (
            previous.resume_id,
            previous.kind,
            previous.input_snapshot.get("source"),
            previous.diagnostic_revision,
        ) != (
            resume_id,
            "compose",
            data.source,
            data.revision,
        ):
            raise BusinessError("重复请求内容不一致。", 409)
        db.session.commit()
        return previous
    from app.services.commerce import ensure_resume_ai_capacity

    ensure_resume_ai_capacity(user_id)
    if resume.revision != data.revision:
        raise BusinessError("简历已更新，请等待保存后重试。", 409)
    if db.session.scalar(
        select(AIOperation.id)
        .where(AIOperation.resume_id == resume_id, AIOperation.state.in_(("queued", "running")))
        .limit(1)
    ):
        raise BusinessError("这份简历已有 AI 任务正在执行。", 409)
    if not is_configured():
        raise BusinessError("AI 服务尚未配置。", 503)
    from app.services.admin_config import runtime_model, runtime_model_route

    model = runtime_model()
    route = runtime_model_route(
        "resume_rewrite", model["model_id"], model.get("fallback_model_ids", [])
    )
    snapshot = {
        "source": data.source,
        "prompt_version": "resume-compose-1",
        "model": route["model_id"],
        "model_candidates": route["model_ids"],
        "model_revision_id": model["revision_id"],
        "model_route_revision_id": route["revision_id"],
    }
    size = len(json.dumps(snapshot, ensure_ascii=False).encode())
    if size > 12000:
        raise BusinessError("整理内容过长，请缩短后重试。", 422)
    item = AIOperation(
        user_id=user_id,
        resume_id=resume_id,
        diagnostic_revision=resume.revision,
        request_key=str(data.request_key),
        kind="compose",
        state="quoted",
        ceiling=0,
        input_snapshot=snapshot,
        expires_at=utcnow() + timedelta(minutes=10),
    )
    db.session.add(item)
    db.session.commit()
    return item


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
    lock_user(user_id)
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
        if snapshot.get("source_facts", "") != data.source_facts.strip():
            raise BusinessError("重复请求内容不一致。", 409)
        db.session.commit()
        return previous
    from app.services.commerce import ensure_resume_ai_capacity

    ensure_resume_ai_capacity(user_id)
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
    if data.source_facts.strip():
        original = data.source_facts.strip()
        context = {"confirmed_facts": original,
                   "boundary": "岗位要求不是用户事实，只整理已提供的经历，不添加技能、指标或经历。"}
    if not isinstance(original, str):
        raise BusinessError("只能改写单条文字。", 422)
    if not original.strip() and (
        data.mode != "generate"
        or not any(isinstance(v, str) and v.strip() for v in context.values())
    ):
        raise BusinessError("请先填写真实内容或同一条目的背景信息。", 422)
    from app.services.admin_config import runtime_model, runtime_model_route

    model = runtime_model()
    route = runtime_model_route(
        "resume_rewrite", model["model_id"], model.get("fallback_model_ids", [])
    )
    snapshot = {
        "path": data.path,
        "source_facts": data.source_facts.strip(),
        "original": original,
        "context": context,
        "mode": data.mode,
        "prompt_version": PROMPT_VERSION,
        "model": route["model_id"],
        "model_candidates": route["model_ids"],
        "model_revision_id": model["revision_id"],
        "model_route_revision_id": route["revision_id"],
    }
    size = len(json.dumps(snapshot, ensure_ascii=False).encode())
    if size > 12000:
        raise BusinessError("改写内容过长，请缩短后重试。", 422)
    item = AIOperation(
        user_id=user_id,
        resume_id=resume_id,
        diagnostic_revision=resume.revision,
        request_key=str(data.request_key),
        kind=data.mode,
        state="quoted",
        ceiling=0,
        input_snapshot=snapshot,
        expires_at=utcnow() + timedelta(minutes=10),
    )
    db.session.add(item)
    db.session.commit()
    return item


def confirm(user_id, operation_id):
    lock_user(user_id)
    item = owned(AIOperation, user_id, operation_id, True)
    if item.resume_id is None:
        raise BusinessError("任务类型不匹配。", 404)
    if item.state != "quoted":
        db.session.commit()
        return item
    resume = owned(Resume, user_id, item.resume_id, True)
    if item.expires_at <= utcnow() or resume.revision != item.diagnostic_revision:
        raise BusinessError("简历已更新，请重试。", 409)
    from app.services.admin_config import runtime_model, runtime_model_route

    model = runtime_model()
    route = runtime_model_route(
        "resume_rewrite", model["model_id"], model.get("fallback_model_ids", [])
    )
    if (
        not is_configured()
        or item.input_snapshot["model"] != route["model_id"]
        or item.input_snapshot.get("model_candidates", [item.input_snapshot["model"]])
        != route["model_ids"]
        or item.input_snapshot["model_revision_id"] != model["revision_id"]
        or item.input_snapshot["model_route_revision_id"] != route["revision_id"]
    ):
        raise BusinessError("模型配置已变化，请重试。", 503)
    item.ceiling = 0
    item.state = "queued"
    db.session.commit()
    return item


def run_operation(operation_id):
    record = db.session.get(AIOperation, operation_id)
    if record is None or record.resume_id is None:
        return
    user_id = record.user_id
    lock_user(user_id)
    item = owned(AIOperation, user_id, operation_id, True)
    if item.state != "queued":
        db.session.commit()
        return
    item.state = "running"
    item.started_at = utcnow()
    snapshot = copy.deepcopy(item.input_snapshot)
    revision = item.diagnostic_revision
    kind = item.kind
    db.session.commit()
    result = None
    tokens = 0
    attempts = 0
    failure_message = "模型超时或输出无效，请稍后重试。"
    from app.services.model_fallback import candidates, model_unavailable
    from app.services.model_provider import generate_resume, generate_resume_document

    provider = (
        current_app.extensions.get(
            "resume_compose_provider" if kind == "compose" else "resume_provider"
        )
        if current_app.testing
        else None
    )

    def save_partial(partial):
        from sqlalchemy.exc import SQLAlchemyError

        try:
            db.session.rollback()
            progress_item = db.session.get(AIOperation, operation_id)
            if progress_item is None or progress_item.state != "running":
                db.session.rollback()
                return
            progress_item.result = {"partial": partial}
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.warning(
                "resume_ai_stream_progress_failed operation=%s", operation_id
            )

    stop_fallback = False
    last_error = None
    model_ids = candidates(snapshot)
    for model_index, model_id in enumerate(model_ids):
        for retry in range(2):
            attempts += 1
            attempt_snapshot = snapshot | {"model": model_id}
            if kind != "compose" and (model_index or retry):
                status = (
                    "模型暂不可用，正在尝试后备模型……"
                    if model_index
                    else "首轮请求失败，正在重试……"
                )
                save_partial({"proposed": "", "reason": status})
            try:
                if provider:
                    raw, usage = provider(attempt_snapshot)
                elif kind == "compose":
                    raw, usage = generate_resume_document(attempt_snapshot)
                else:
                    raw, usage = generate_resume(attempt_snapshot, on_progress=save_partial)
                if not isinstance(usage, int) or not 0 < usage <= 2000000:
                    raise ValueError("费用用量不可用")
                tokens += usage
                if kind == "compose":
                    output = ResumeComposeOutput.model_validate(raw)
                    document = output.document.model_dump()
                    if (
                        document["photo"]
                        or len(document["skills"]) > 4
                        or len(json.dumps(document, ensure_ascii=False)) > 30000
                    ):
                        raise ValueError("简历草稿包含不支持的内容")
                    source_numbers = set(re.findall(r"\d+(?:[.,]\d+)?%?", snapshot["source"]))
                    draft_numbers = set(
                        re.findall(r"\d+(?:[.,]\d+)?%?", json.dumps(document, ensure_ascii=False))
                    )
                    if not draft_numbers.issubset(source_numbers):
                        raise ValueError("简历草稿新增了未经确认的数字")
                    result = {"document": document, "reason": output.reason, "revision": revision}
                else:
                    output = ResumeAIOutput.model_validate(raw)
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
                last_error = error
                status_code = getattr(error, "status_code", None)
                if status_code == 402:
                    failure_message = "AI 服务暂不可用，请联系管理员处理；你的会员权益不受影响。"
                elif status_code == 401:
                    failure_message = "模型服务密钥无效，请联系管理员。"
                elif status_code == 429:
                    failure_message = "模型服务请求过于频繁，请稍后重试。"
                current_app.logger.warning(
                    "resume_ai_attempt_failed operation=%s model_index=%s type=%s",
                    operation_id,
                    model_index,
                    type(error).__name__,
                )
                if retry == 1 and not model_unavailable(error):
                    stop_fallback = True
                    break
        if result is not None or stop_fallback:
            break
    if result is None and last_error is not None and model_unavailable(last_error):
        failure_message = "已尝试配置的模型，仍不可用，请稍后重试。"
    lock_user(user_id)
    item = owned(AIOperation, user_id, operation_id, True)
    if item.state != "running":
        db.session.commit()
        return
    item.attempts = attempts
    item.tokens = tokens
    if result is None:
        item.result = None
        release(item, "failed", failure_message)
    else:
        item.result = result
        item.ceiling = 0
        item.charged = 0
        item.state = "succeeded"
    db.session.commit()
