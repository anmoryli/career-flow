import copy
import json
import math
from datetime import timedelta

from flask import current_app
from sqlalchemy import and_, or_, select

from app.career_schemas import ResumeDocument, ResumeSave
from app.diagnosis_schemas import DiagnosisOutput, DiagnosisResult
from app.extensions import db
from app.models import (
    AIOperation,
    Conversation,
    ConversationMessage,
    CreditAccount,
    CreditEntry,
    Diagnostic,
    DiagnosticAnswer,
    JobTarget,
    ResumeVersion,
    User,
    utcnow,
)
from app.services.career import owned, save_resume
from app.services.errors import BusinessError

PROMPT_VERSION = "career-diagnosis-1"


def owner_lock(user_id):
    db.session.scalar(select(User).where(User.id == user_id).with_for_update())


def account(user_id):
    item = db.session.scalar(
        select(CreditAccount)
        .where(CreditAccount.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None:
        item = CreditAccount(user_id=user_id, available=0, frozen=0)
        db.session.add(item)
        db.session.flush()
    return item


def get_diagnostic(user_id, job_id):
    owner_lock(user_id)
    job = owned(JobTarget, user_id, job_id)
    item = db.session.scalar(
        select(Diagnostic).where(Diagnostic.job_id == job.id).with_for_update()
    )
    if item is None:
        conversation = Conversation(user_id=user_id, title=job.title or "岗位诊断")
        db.session.add(conversation)
        db.session.flush()
        item = Diagnostic(
            user_id=user_id,
            job_id=job.id,
            conversation_id=conversation.id,
            rounds=0,
            revision=0,
            state="active",
            question="",
        )
        db.session.add(item)
    db.session.commit()
    return item


def is_configured():
    from app.services.admin_config import runtime_model

    model = runtime_model()
    return bool(model["model_id"] and model["secret"] and model["enabled"]) or (
        current_app.testing and "diagnosis_provider" in current_app.extensions
    )


def active_operation(diagnostic_id):
    return db.session.scalar(
        select(AIOperation.id)
        .where(
            AIOperation.diagnostic_id == diagnostic_id,
            AIOperation.state.in_(["queued", "running"]),
        )
        .limit(1)
        .with_for_update()
    )


def quote(user_id, diagnostic_id, data):
    owner_lock(user_id)
    diagnostic = owned(Diagnostic, user_id, diagnostic_id, True)
    previous = db.session.scalar(
        select(AIOperation)
        .where(AIOperation.user_id == user_id, AIOperation.request_key == str(data.request_key))
        .with_for_update()
    )
    if previous:
        if previous.diagnostic_id != diagnostic.id or previous.kind != data.kind:
            raise BusinessError("重复请求不一致。", 409)
        db.session.commit()
        return previous
    if diagnostic.state == "completed" or active_operation(diagnostic.id):
        raise BusinessError("诊断已完成或任务正在执行。", 409)
    if not is_configured():
        raise BusinessError("真实 AI 尚未配置，不能确认费用或启动诊断。", 503)
    if data.kind == "analysis" and diagnostic.rounds >= 10:
        raise BusinessError("追问已达十轮，请生成报告。", 409)
    job = owned(JobTarget, user_id, diagnostic.job_id)
    version = db.session.get(ResumeVersion, job.resume_version_id)
    answers = db.session.scalars(
        select(DiagnosticAnswer)
        .where(DiagnosticAnswer.diagnostic_id == diagnostic.id)
        .order_by(DiagnosticAnswer.round)
    ).all()
    document = dict(version.document)
    document.pop("photo", None)  # A text model never needs the user's photo.
    for section in document.get("hidden_sections", []):
        document[section] = "" if section == "summary" else []
    from app.services.admin_config import (
        runtime_diagnosis_prompt,
        runtime_model,
        runtime_model_route,
    )

    model = runtime_model()
    prompt = runtime_diagnosis_prompt()
    route = runtime_model_route(data.kind, model["model_id"])
    snapshot = {
        "document": document,
        "jd": job.description,
        "answers": [
            {"question": a.question, "answer": a.answer, "skipped": a.skipped} for a in answers
        ],
        "kind": data.kind,
        "rounds": diagnostic.rounds,
        "prompt_version": (
            f"career-diagnosis-{prompt['version']}" if prompt["revision_id"] else PROMPT_VERSION
        ),
        "prompt_revision_id": prompt["revision_id"],
        "prompt_instructions": prompt["instructions"],
        "model": route["model_id"],
        "model_revision_id": model["revision_id"],
        "model_route_revision_id": route["revision_id"],
        "tokens_per_credit": model["tokens_per_credit"],
    }
    input_bytes = len(json.dumps(snapshot, ensure_ascii=False).encode())
    if input_bytes > 100000:
        raise BusinessError("本次诊断文字过长，请缩减重复经历或岗位描述后重试。", 422)
    # Conservative UTF-8 upper bound + output/schema budget, both attempts included.
    ceiling = math.ceil(2 * (input_bytes + 24000) / snapshot["tokens_per_credit"])
    item = AIOperation(
        user_id=user_id,
        diagnostic_id=diagnostic.id,
        request_key=str(data.request_key),
        kind=data.kind,
        diagnostic_revision=diagnostic.revision,
        ceiling=ceiling,
        input_snapshot=snapshot,
        state="quoted",
        expires_at=utcnow() + timedelta(minutes=10),
    )
    db.session.add(item)
    db.session.commit()
    return item


def confirm(user_id, operation_id):
    owner_lock(user_id)
    item = owned(AIOperation, user_id, operation_id, True)
    if item.state != "quoted":
        db.session.commit()
        return item
    diagnostic = owned(Diagnostic, user_id, item.diagnostic_id, True)
    if (
        item.expires_at <= utcnow()
        or diagnostic.revision != item.diagnostic_revision
        or diagnostic.state == "completed"
        or active_operation(diagnostic.id)
    ):
        raise BusinessError("费用预估已过期或诊断已更新，请重新预估。", 409)
    from app.services.admin_config import (
        runtime_diagnosis_prompt,
        runtime_model,
        runtime_model_route,
    )

    model = runtime_model()
    prompt = runtime_diagnosis_prompt()
    route = runtime_model_route(item.kind, model["model_id"])
    if (
        not is_configured()
        or item.input_snapshot["model"] != route["model_id"]
        or item.input_snapshot.get("model_revision_id") != model["revision_id"]
        or item.input_snapshot.get("model_route_revision_id") != route["revision_id"]
        or item.input_snapshot.get("prompt_revision_id") != prompt["revision_id"]
    ):
        raise BusinessError("模型配置不可用或已改变，请重新预估。", 503)
    balance = account(user_id)
    if balance.available < item.ceiling:
        raise BusinessError("可用积分不足，尚未扣费。", 409)
    balance.available -= item.ceiling
    balance.frozen += item.ceiling
    db.session.add(
        CreditEntry(
            user_id=user_id,
            operation_id=item.id,
            kind="freeze",
            available_delta=-item.ceiling,
            frozen_delta=item.ceiling,
        )
    )
    item.state = "queued"
    db.session.commit()
    return item


def release(item, state, error=""):
    balance = account(item.user_id)
    balance.available += item.ceiling
    balance.frozen -= item.ceiling
    db.session.add(
        CreditEntry(
            user_id=item.user_id,
            operation_id=item.id,
            kind="release",
            available_delta=item.ceiling,
            frozen_delta=-item.ceiling,
        )
    )
    item.state = state
    item.error = error


def cancel(user_id, operation_id):
    owner_lock(user_id)
    item = owned(AIOperation, user_id, operation_id, True)
    if item.state in {"queued", "running"}:
        release(item, "cancelled")
    elif item.state == "quoted":
        item.state = "cancelled"
    db.session.commit()
    return item


def answer(user_id, diagnostic_id, data):
    owner_lock(user_id)
    item = owned(Diagnostic, user_id, diagnostic_id, True)
    previous = db.session.scalar(
        select(DiagnosticAnswer)
        .where(
            DiagnosticAnswer.diagnostic_id == item.id,
            DiagnosticAnswer.request_key == str(data.request_key),
        )
        .with_for_update()
    )
    if previous:
        if previous.answer != data.answer or previous.skipped != data.skipped:
            raise BusinessError("重复回答内容不一致。", 409)
        db.session.commit()
        return item
    if (
        item.state != "active"
        or not item.question
        or item.rounds >= 10
        or item.revision != data.revision
        or active_operation(item.id)
    ):
        raise BusinessError("当前不能提交回答，请重新载入诊断。", 409)
    from app.services.interactions import active_question, record_question_answer

    interaction = active_question(item.conversation_id)
    if interaction:
        if interaction.definition["message"] != item.question:
            raise BusinessError("问题已经更新，请重新载入诊断。", 409)
        record_question_answer(interaction, str(data.request_key), data.answer, data.skipped)
    item.rounds += 1
    item.revision += 1
    db.session.add(
        DiagnosticAnswer(
            diagnostic_id=item.id,
            round=item.rounds,
            request_key=str(data.request_key),
            question=item.question,
            answer=data.answer,
            skipped=data.skipped,
        )
    )
    db.session.add(
        ConversationMessage(
            conversation_id=item.conversation_id,
            role="user",
            content="跳过" if data.skipped else data.answer,
            request_key=str(data.request_key),
        )
    )
    item.question = ""
    db.session.commit()
    return item


def get_path(document, path):
    value = document
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def validate_output(raw, snapshot):
    output = DiagnosisOutput.model_validate(raw)

    def text_values(value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [text for child in value.values() for text in text_values(child)]
        if isinstance(value, list):
            return [text for child in value for text in text_values(child)]
        return []

    resume_text = text_values(snapshot["document"])
    answers_text = [entry["answer"] for entry in snapshot["answers"] if not entry["skipped"]]
    for finding in output.findings:
        if finding.requirement not in snapshot["jd"]:
            raise ValueError("岗位证据未找到")
        source = resume_text if finding.source == "resume" else answers_text
        if finding.source == "none":
            if finding.evidence:
                raise ValueError("缺失信息不能伪造证据")
        elif not finding.evidence or not any(finding.evidence in text for text in source):
            raise ValueError("简历证据未找到")
    for suggestion in output.suggestions:
        if get_path(snapshot["document"], suggestion.path) != suggestion.original:
            raise ValueError("建议原文不匹配")
        candidate = copy.deepcopy(snapshot["document"])
        parts = suggestion.path.split(".")
        parent = get_path(candidate, ".".join(parts[:-1])) if len(parts) > 1 else candidate
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        parent[key] = suggestion.proposed
        ResumeDocument.model_validate(candidate)
    if len({s.path for s in output.suggestions}) != len(output.suggestions):
        raise ValueError("建议不能重复修改同一段原文")
    if snapshot["kind"] == "report" or snapshot["rounds"] >= 10:
        output.question = ""
    if output.question.count("？") + output.question.count("?") > 1:
        raise ValueError("每轮只能追问一个问题")
    result = output.model_dump()
    result["overall_score"] = sum(d.score for d in output.dimensions) / 5
    return DiagnosisResult.model_validate(result).model_dump()


def run_operation(operation_id):
    """RQ entry body; no transaction is held during provider requests."""
    record = db.session.get(AIOperation, operation_id)
    if not record:
        return
    user_id = record.user_id
    owner_lock(user_id)
    item = owned(AIOperation, user_id, operation_id, True)
    if item.state != "queued":
        db.session.commit()
        return
    item.state = "running"
    item.started_at = utcnow()
    snapshot = copy.deepcopy(item.input_snapshot)
    db.session.commit()
    result = None
    tokens = 0
    attempts = 0
    for attempt in range(2):
        attempts = attempt + 1
        try:
            from app.services.model_provider import generate

            provider = (
                current_app.extensions.get("diagnosis_provider") if current_app.testing else None
            )
            raw, usage = (provider or generate)(snapshot)
            if not isinstance(usage, int) or not 0 < usage <= 2000000:
                raise ValueError("费用用量不可用")
            tokens += usage
            result = validate_output(raw, snapshot)
            break
        except Exception as error:
            # Never persist provider exception strings (may contain credentials/documents).
            current_app.logger.warning(
                "ai_attempt_failed operation=%s type=%s", operation_id, type(error).__name__
            )
    owner_lock(user_id)
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
        balance = account(user_id)
        balance.available += item.ceiling - charged
        balance.frozen -= item.ceiling
        db.session.add(
            CreditEntry(
                user_id=user_id,
                operation_id=item.id,
                kind="settle",
                available_delta=item.ceiling - charged,
                frozen_delta=-item.ceiling,
            )
        )
        item.result = result
        item.charged = charged
        item.state = "succeeded"
        diagnostic = owned(Diagnostic, user_id, item.diagnostic_id, True)
        diagnostic.revision += 1
        diagnostic.question = result["question"]
        from app.services.interactions import active_question, question_interaction

        previous_question = active_question(diagnostic.conversation_id)
        if previous_question:
            previous_question.state = "superseded"
        if result["question"] and item.kind != "report":
            question_interaction(diagnostic.conversation_id, item.id, result["question"])
        if item.kind == "report":
            diagnostic.state = "completed"
            db.session.get(Conversation, diagnostic.conversation_id).status = "readonly"
        db.session.add(
            ConversationMessage(
                conversation_id=diagnostic.conversation_id,
                role="assistant",
                content=json.dumps(result, ensure_ascii=False),
                request_key=item.request_key,
            )
        )
    db.session.commit()


def apply_suggestions(user_id, operation_id, data):
    item = owned(AIOperation, user_id, operation_id)
    if item.state != "succeeded":
        raise BusinessError("任务尚未完成。", 409)
    diagnostic = owned(Diagnostic, user_id, item.diagnostic_id)
    job = owned(JobTarget, user_id, diagnostic.job_id)
    version = db.session.get(ResumeVersion, job.resume_version_id)
    document = copy.deepcopy(version.document)
    suggestions = item.result["suggestions"]
    if not set(data.edits).issubset(data.indices):
        raise BusinessError("只能编辑已选择的建议。", 422)
    for index in dict.fromkeys(data.indices):
        if index < 0 or index >= len(suggestions):
            raise BusinessError("建议编号无效。", 422)
        suggestion = suggestions[index]
        parts = suggestion["path"].split(".")
        parent = get_path(document, ".".join(parts[:-1])) if len(parts) > 1 else document
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        parent[key] = data.edits.get(index, suggestion["proposed"])
    document["photo"] = version.document.get("photo", "")
    return save_resume(
        user_id,
        ResumeSave(
            request_key=data.request_key,
            title=data.title,
            template=version.template,
            document=document,
        ),
        parent_id=version.resume_id,
    )


def recover_stale_tasks():
    from app.models import ResumeImport

    cutoff = utcnow() - timedelta(minutes=5)
    ids = db.session.scalars(
        select(AIOperation.id).where(
            or_(
                and_(AIOperation.state == "queued", AIOperation.created_at < cutoff),
                and_(AIOperation.state == "running", AIOperation.started_at < cutoff),
            )
        )
    ).all()
    recovered = 0
    for operation_id in ids:
        record = db.session.get(AIOperation, operation_id)
        owner_lock(record.user_id)
        item = owned(AIOperation, record.user_id, operation_id, True)
        stale = (item.state == "queued" and item.created_at < cutoff) or (
            item.state == "running" and (item.started_at or item.created_at) < cutoff
        )
        if stale:
            release(item, "failed", "后台任务中断或超时，冻结积分已释放，请重新预估。")
            recovered += 1
        db.session.commit()
    imports = db.session.scalars(
        select(ResumeImport)
        .where(ResumeImport.state.in_(["queued", "running"]), ResumeImport.created_at < cutoff)
        .with_for_update()
    ).all()
    for item in imports:
        item.state = "failed"
        item.content = None
        item.error = "解析任务中断或超时，请重新导入。"
        recovered += 1
    db.session.commit()
    return recovered
