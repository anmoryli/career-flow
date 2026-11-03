import copy
import json
import time
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
    Diagnostic,
    DiagnosticAnswer,
    JobTarget,
    Resume,
    utcnow,
)
from app.services.career import owned, save_resume
from app.services.commerce import ensure_job_analysis_capacity
from app.services.commerce import lock_user as owner_lock
from app.services.errors import BusinessError
from app.services.operation_events import publish as publish_event

PROMPT_VERSION = "career-diagnosis-1"

# Stage copy for the analysis chat panel. Kept server-side so a copy change is
# one edit, not one edit per template.
STAGE_MESSAGES = {
    "queued": "分析已排队，稍等一会儿就开始。",
    "parsing": "正在拆解岗位要求，并回到简历里找对应证据。",
    "reporting": "正在整理报告结构，逐个核对证据与缺口。",
}


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
        current_app.testing
        and (
            "diagnosis_provider" in current_app.extensions
            or "resume_provider" in current_app.extensions
        )
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
    # Verify ownership before revealing account entitlement state. A foreign
    # diagnostic must remain indistinguishable from a missing one.
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
    ensure_job_analysis_capacity(user_id,diagnostic.id,data.kind)
    if diagnostic.state == "completed" or active_operation(diagnostic.id):
        raise BusinessError("诊断已完成或任务正在执行。", 409)
    if not is_configured():
        raise BusinessError("真实 AI 尚未配置，暂时无法启动诊断。", 503)
    if data.kind == "analysis" and diagnostic.rounds >= 10:
        raise BusinessError("追问已达十轮，请生成报告。", 409)
    job = owned(JobTarget, user_id, diagnostic.job_id)
    resume = owned(Resume, user_id, job.resume_id)
    answers = db.session.scalars(
        select(DiagnosticAnswer)
        .where(DiagnosticAnswer.diagnostic_id == diagnostic.id)
        .order_by(DiagnosticAnswer.round)
    ).all()
    document = dict(resume.document)
    document.pop("photo", None)  # A text model never needs the user's photo.
    hidden_sections = document.get("hidden_sections", [])
    hidden_custom_ids = {
        section.removeprefix("custom:")
        for section in hidden_sections
        if section.startswith("custom:")
    }
    if hidden_custom_ids:
        document["custom_sections"] = [
            section
            for section in document.get("custom_sections", [])
            if section.get("id") not in hidden_custom_ids
        ]
    for section in hidden_sections:
        if section.startswith("custom:"):
            continue
        document[section] = "" if section == "summary" else []
    from app.services.admin_config import (
        runtime_diagnosis_prompt,
        runtime_model,
        runtime_model_route,
    )

    model = runtime_model()
    prompt = runtime_diagnosis_prompt()
    route = runtime_model_route(
        data.kind, model["model_id"], model.get("fallback_model_ids", [])
    )
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
        "output_contract_version": "diagnosis-references-1",
        "prompt_revision_id": prompt["revision_id"],
        "prompt_instructions": prompt["instructions"],
        "model": route["model_id"],
        "model_candidates": route["model_ids"],
        "model_revision_id": model["revision_id"],
        "model_route_revision_id": route["revision_id"],
    }
    input_bytes = len(json.dumps(snapshot, ensure_ascii=False).encode())
    if input_bytes > 100000:
        raise BusinessError("本次诊断文字过长，请缩减重复经历或岗位描述后重试。", 422)
    from app.services.product import prepare_snapshot
    prepare_snapshot(user_id,snapshot)
    item = AIOperation(
        user_id=user_id,
        diagnostic_id=diagnostic.id,
        request_key=str(data.request_key),
        kind=data.kind,
        diagnostic_revision=diagnostic.revision,
        ceiling=0,
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
    if item.diagnostic_id is None:
        raise BusinessError("任务类型不匹配。", 404)
    if item.state != "quoted":
        db.session.commit()
        return item
    diagnostic = owned(Diagnostic, user_id, item.diagnostic_id, True)
    if item.expires_at <= utcnow():
        raise BusinessError("报价已过期，请重新开始本次操作。", 409)
    if (
        diagnostic.revision != item.diagnostic_revision
        or diagnostic.state == "completed"
        or active_operation(diagnostic.id)
    ):
        raise BusinessError("诊断已更新，请重试。", 409)
    from app.services.admin_config import (
        runtime_diagnosis_prompt,
        runtime_model,
        runtime_model_route,
    )

    model = runtime_model()
    prompt = runtime_diagnosis_prompt()
    route = runtime_model_route(
        item.kind, model["model_id"], model.get("fallback_model_ids", [])
    )
    if not is_configured():
        raise BusinessError("AI 服务暂不可用，请稍后重试。", 503)
    if (
        item.input_snapshot.get("standard_model", item.input_snapshot["model"])
        != route["model_id"]
        or item.input_snapshot.get(
            "standard_model_candidates",
            item.input_snapshot.get("model_candidates", [item.input_snapshot["model"]]),
        )
        != route["model_ids"]
        or item.input_snapshot.get("model_revision_id") != model["revision_id"]
        or item.input_snapshot.get("model_route_revision_id") != route["revision_id"]
        or item.input_snapshot.get("prompt_revision_id") != prompt["revision_id"]
    ):
        raise BusinessError("模型配置已更新，请重新启动本次操作。", 409)
    ensure_job_analysis_capacity(user_id,diagnostic.id,item.kind,exclude=item.id)
    from app.services.product import prepare_snapshot, record_event

    snapshot = dict(item.input_snapshot)
    prepare_snapshot(user_id, snapshot, exclude=item.id)
    item.input_snapshot = snapshot
    item.ceiling = 0
    item.state = "queued"
    record_event(user_id,"diagnosis_started",f"start:{item.id}",operation_id=item.id,diagnostic_id=diagnostic.id)
    db.session.commit()
    return item


def release(item, state, error=""):
    item.ceiling = 0
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
    from app.services.product import ensure_full_access
    ensure_full_access(user_id)
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
    if snapshot.get("access_tier")=="free_preview":
        result["suggestions"] = []
        result["question"] = ""
    result["overall_score"] = sum(d.score for d in output.dimensions) / 5
    return DiagnosisResult.model_validate(result).model_dump()


def run_operation(operation_id):
    """RQ entry body; no transaction is held during provider requests."""
    record = db.session.get(AIOperation, operation_id)
    if not record or record.diagnostic_id is None:
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
    from app.services.product import TokenUsage, call_usage, policy, record_event, store_call_usage
    usage_policy, usage_policy_revision = policy()
    calls = []
    job_title = db.session.scalar(
        select(JobTarget.title)
        .join(Diagnostic, Diagnostic.job_id == JobTarget.id)
        .where(Diagnostic.id == item.diagnostic_id)
    ) or ""
    db.session.commit()
    publish_event(
        operation_id,
        "stage",
        {
            "message": STAGE_MESSAGES[
                "reporting" if snapshot.get("kind") == "report" else "parsing"
            ],
            "kind": snapshot.get("kind") or "analysis",
        },
    )
    result = None
    tokens = 0
    attempts = 0
    from app.services.model_fallback import candidates, model_unavailable
    from app.services.model_provider import generate
    from app.services.model_runtime import provider_error

    provider = current_app.extensions.get("diagnosis_provider") if current_app.testing else None
    orchestrated = (
        provider is None
        and bool(current_app.config.get("DIAGNOSIS_AGENT_ENABLED"))
        and snapshot.get("access_tier") != "free_preview"
    )
    stop_fallback = False
    last_error = None
    if orchestrated:
        # Deep-agents run: plan, delegate per-section evidence audits, then a
        # single structured write-back. Validation gates are identical to the
        # single-shot pipeline; a failed orchestration degrades to it below.
        from app.services.agent_orchestrator import run_diagnosis_agent

        for retry in range(2):
            attempt_started = time.monotonic()
            try:
                raw, agent_calls, agent_tokens = run_diagnosis_agent(snapshot)
                tokens += agent_tokens
                for offset, call in enumerate(agent_calls):
                    usage = (
                        TokenUsage(call["total"], call["input"], call["output"])
                        if call["total"]
                        else None
                    )
                    calls.append(
                        call_usage(
                            attempts + offset + 1,
                            snapshot["model"],
                            usage,
                            usage_policy,
                            call["outcome"],
                        )
                    )
                attempts += len(agent_calls)
                result = validate_output(raw, snapshot)
                break
            except Exception as error:
                attempts += 1
                if not calls or calls[-1]["attempt"] != attempts:
                    calls.append(
                        call_usage(
                            attempts, snapshot["model"], None, usage_policy, "provider_error"
                        )
                    )
                last_error = provider_error(error)
                current_app.logger.warning(
                    "agent_orchestrator_failed operation=%s type=%s cause=%s "
                    "retry=%s elapsed_seconds=%.3f",
                    operation_id,
                    type(error).__name__,
                    type(last_error).__name__,
                    retry + 1,
                    time.monotonic() - attempt_started,
                )
        if result is None:
            # Degrade to the deterministic single-shot pipeline so a member
            # task never fails because the orchestration layer struggled.
            current_app.logger.warning(
                "agent_orchestrator_degraded operation=%s falling_back=single_shot",
                operation_id,
            )
            fallback_models = candidates(snapshot)
        else:
            fallback_models = []
    else:
        fallback_models = candidates(snapshot)
    for model_index, model_id in enumerate(fallback_models):
        for retry in range(2):
            attempts += 1
            attempt_started = time.monotonic()
            try:
                raw, usage = (provider or generate)(snapshot | {"model": model_id})
                if not isinstance(usage, int) or not 0 < usage <= 2000000:
                    raise ValueError("费用用量不可用")
                tokens += usage
                calls.append(call_usage(attempts,model_id,usage,usage_policy,"returned"))
                result = validate_output(raw, snapshot)
                break
            except Exception as error:
                if not calls or calls[-1]["attempt"]!=attempts:
                    calls.append(call_usage(attempts,model_id,None,usage_policy,"provider_error"))
                else:
                    calls[-1]["outcome"]="invalid_output"
                last_error = provider_error(error)
                # Never persist provider exception strings (may contain credentials/documents).
                current_app.logger.warning(
                    "ai_attempt_failed operation=%s model_index=%s type=%s status=%s "
                    "cause=%s attempt=%s elapsed_seconds=%.3f",
                    operation_id,
                    model_index,
                    type(error).__name__,
                    getattr(last_error, "status_code", None),
                    type(last_error).__name__,
                    retry + 1,
                    time.monotonic() - attempt_started,
                )
                if retry == 1 and not model_unavailable(error):
                    stop_fallback = True
                    break
        if result is not None or stop_fallback:
            break
    owner_lock(user_id)
    item = owned(AIOperation, user_id, operation_id, True)
    try:
        store_call_usage(item, calls, usage_policy_revision)
    except Exception as error:
        # A ledger lock conflict must not turn a finished analysis into a
        # failed one; the spend stays visible through the operation's token
        # counter and the warning below.
        db.session.rollback()
        item = owned(AIOperation, user_id, operation_id, True)
        current_app.logger.warning(
            "diagnosis_metering_failed operation=%s type=%s",
            operation_id,
            type(error).__name__,
        )
    if item.state != "running":
        db.session.commit()
        return
    item.attempts = attempts
    item.tokens = tokens
    if result is None:
        status = getattr(last_error, "status_code", None)
        if status in {401, 403}:
            failure = "模型服务认证失败，请检查 API Key 和模型访问权限。"
        elif status == 402:
            failure = "AI 服务暂不可用，请联系管理员处理；你的会员权益不受影响。"
        elif status == 404:
            failure = "模型接口或模型 ID 不存在，请检查 API 地址和模型 ID。"
        elif status == 429:
            failure = "模型服务请求频率受限，请稍后重试或检查服务商额度。"
        elif isinstance(last_error, (TimeoutError,)) or type(last_error).__name__ in {
            "APITimeoutError",
            "ReadTimeout",
            "ConnectTimeout",
        }:
            failure = "连接模型服务超时，请检查服务商状态和网络后重试。"
        elif isinstance(last_error, ValueError) or type(last_error).__name__ == "ValidationError":
            failure = "模型返回内容不符合诊断格式，请检查模型配置后重试。"
        else:
            failure = "模型服务暂时不可用，请稍后重试。"
        release(item, "failed", failure)
    else:
        item.result = result
        item.ceiling = 0
        item.charged = 0
        item.state = "succeeded"
        diagnostic = owned(Diagnostic, user_id, item.diagnostic_id, True)
        diagnostic.revision += 1
        diagnostic.question = result["question"]
        record_event(
            user_id,
            "report_completed" if item.kind == "report" else "diagnosis_completed",
            f"done:{item.id}",
            operation_id=item.id,
            diagnostic_id=diagnostic.id,
        )
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
    # Announce only after the outcome is durable: the panel reloads
    # authoritative state the moment it sees one of these events.
    if result is None:
        publish_event(operation_id, "failed", {"message": failure})
        return
    publish_event(
        operation_id,
        "result",
        {"operation_id": operation_id, "kind": item.kind},
    )
    # A recap is never allowed to keep the panel waiting: whatever happens
    # here, `done` still has to reach the browser.
    try:
        stream_summary(
            operation_id,
            snapshot | {"job_title": job_title},
            result,
            calls=calls,
            usage_policy=usage_policy,
            usage_policy_revision=usage_policy_revision,
            first_attempt=attempts + 1,
        )
    except Exception as error:
        db.session.rollback()
        current_app.logger.warning(
            "diagnosis_summary_persist_failed operation=%s type=%s",
            operation_id,
            type(error).__name__,
        )
    publish_event(operation_id, "done", {"operation_id": operation_id, "kind": item.kind})


def stream_summary(
    operation_id,
    snapshot,
    result,
    *,
    calls,
    usage_policy,
    usage_policy_revision,
    first_attempt,
):
    """Stream a short recap of a finished analysis into the chat panel.

    Best-effort by design: the analysis is already saved and paid for, so a
    recap failure only costs the recap. Its tokens are still metered, because
    they are real spend.
    """
    from app.services.model_provider import summarize_diagnosis
    from app.services.product import call_usage, store_call_usage

    chunks = []

    def on_delta(delta):
        chunks.append(delta)
        publish_event(operation_id, "delta", {"text": delta})

    # Fixture servers inject a deterministic recap so browser runs never reach
    # a paid provider; production uses the real summariser.
    summarize = (
        current_app.extensions.get("diagnosis_summary_provider") or summarize_diagnosis
    )
    try:
        usage = summarize(snapshot, result, on_delta)
    except Exception as error:
        current_app.logger.warning(
            "diagnosis_summary_failed operation=%s type=%s",
            operation_id,
            type(error).__name__,
        )
        if chunks:
            # Do not leave a half sentence on screen.
            publish_event(operation_id, "delta_reset", {})
        return
    item = db.session.get(AIOperation, operation_id)
    if item is None:
        return
    # Persisted so a reload rebuilds the conversation instead of losing the
    # recap the user just watched arrive.
    note = "".join(chunks)[:4000]
    try:
        call = call_usage(first_attempt, snapshot["model"], usage, usage_policy, "returned")
        store_call_usage(item, [call], usage_policy_revision)
        item.tokens = (item.tokens or 0) + int(usage)
        item.note = note
        calls.append(call)
        db.session.commit()
    except Exception as error:
        # Metering sits beside the recap, not in front of it: on a lock
        # conflict, keep what the user reads back and drop only the ledger row.
        db.session.rollback()
        current_app.logger.warning(
            "diagnosis_summary_metering_failed operation=%s type=%s",
            operation_id,
            type(error).__name__,
        )
        item = db.session.get(AIOperation, operation_id)
        if item is not None:
            item.note = note
            db.session.commit()


def apply_suggestions(user_id, operation_id, data):
    item = owned(AIOperation, user_id, operation_id)
    if item.diagnostic_id is None:
        raise BusinessError("任务类型不匹配。", 404)
    if item.state != "succeeded":
        raise BusinessError("任务尚未完成。", 409)
    diagnostic = owned(Diagnostic, user_id, item.diagnostic_id)
    job = owned(JobTarget, user_id, diagnostic.job_id)
    resume = owned(Resume, user_id, job.resume_id)
    document = copy.deepcopy(resume.document)
    from app.services.product import ensure_full_access
    ensure_full_access(user_id,item)
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
    from app.services.diagnosis_references import editable_targets

    allowed = {target["path"] for target in editable_targets(resume.document).values()}
    if not set(data.paragraph_edits).issubset(allowed):
        raise BusinessError("只能修改本次简历中已有的可编辑段落。", 422)
    selected_paths = {suggestions[index]["path"] for index in data.indices}
    if selected_paths.intersection(data.paragraph_edits):
        raise BusinessError("同一段落不能重复提交修改。", 422)
    for path, text in data.paragraph_edits.items():
        parts = path.split(".")
        parent = get_path(document, ".".join(parts[:-1])) if len(parts) > 1 else document
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        parent[key] = text
    if data.additions:
        from uuid import NAMESPACE_URL, uuid5

        sections = document.setdefault("custom_sections", [])
        if len(sections) + len(data.additions) > 10:
            raise BusinessError("补充板块最多10个，请在编辑器中合并后再保存。", 422)
        for index, content in enumerate(data.additions):
            section_id = str(
                uuid5(NAMESPACE_URL, f"careerflow:{user_id}:{data.request_key}:{index}")
            )
            sections.append({"id": section_id, "title": "岗位相关补充", "content": content})
            document.setdefault("section_order", []).append(f"custom:{section_id}")
    document["photo"] = resume.document.get("photo", "")
    return save_resume(
        user_id,
        ResumeSave(
            request_key=data.request_key,
            title=data.title,
            template=resume.template,
            document=document,
        ),
        parent_id=resume.id,
        source_operation_id=item.id,
    )


def recover_stale_tasks():
    from app.models import ResumeImport
    from app.services.model_runtime import diagnosis_job_seconds

    now = utcnow()
    cutoff = now - timedelta(minutes=5)
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
        running_cutoff = (
            now - timedelta(seconds=diagnosis_job_seconds(item.input_snapshot) + 30)
            if item.diagnostic_id is not None
            else cutoff
        )
        stale = (item.state == "queued" and item.created_at < cutoff) or (
            item.state == "running" and (item.started_at or item.created_at) < running_cutoff
        )
        if stale:
            release(item, "failed", "后台任务中断或超时，请重试。")
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
