"""Validated, persisted interaction state. Model output is always untrusted."""

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from app.extensions import db
from app.models import StructuredInteraction, utcnow
from app.schemas import StructuredMessage
from app.services.errors import BusinessError


def question_interaction(conversation_id: int, operation_id: int, question: str):
    definition = StructuredMessage.model_validate(
        {
            "schema_version": "1.0",
            "message": question,
            "blocks": [
                {
                    "type": "form",
                    "id": str(uuid4()),
                    "fields": [
                        {
                            "name": "answer",
                            "label": "你的回答",
                            "type": "textarea",
                            "required": True,
                        }
                    ],
                }
            ],
            "conversation_state": "waiting_for_user",
        }
    )
    item = StructuredInteraction(
        conversation_id=conversation_id,
        operation_id=operation_id,
        definition=definition.model_dump(mode="json"),
        state="waiting_for_user",
    )
    db.session.add(item)
    return item


def active_question(conversation_id: int):
    return db.session.scalar(
        select(StructuredInteraction)
        .where(
            StructuredInteraction.conversation_id == conversation_id,
            StructuredInteraction.state == "waiting_for_user",
        )
        .order_by(StructuredInteraction.id.desc())
        .limit(1)
    )


def validate_values(definition: dict, values: dict) -> dict:
    try:
        message = StructuredMessage.model_validate(definition)
    except ValidationError:
        raise BusinessError("表单定义已失效，请重新载入。", 409) from None
    fields = [field for block in message.blocks for field in block.fields]
    if len({field.name for field in fields}) != len(fields):
        raise BusinessError("表单定义有重复字段。", 409)
    if set(values) - {field.name for field in fields}:
        raise BusinessError("提交包含表单以外的字段。", 422)
    cleaned = {}
    for field in fields:
        value = values.get(field.name)
        if value is None or value == "" or value == []:
            if field.required:
                raise BusinessError(f"请填写{field.label}。", 422)
            continue
        if field.type == "checkbox":
            if type(value) is not bool:
                raise BusinessError(f"{field.label}必须为勾选状态。", 422)
        elif field.type == "multiselect":
            if (
                not isinstance(value, list)
                or len(value) > 50
                or any(
                    not isinstance(option, str) or option not in field.options for option in value
                )
                or len(set(value)) != len(value)
            ):
                raise BusinessError(f"{field.label}选项无效。", 422)
        elif field.type in {"select", "radio"}:
            if not isinstance(value, str) or value not in field.options:
                raise BusinessError(f"{field.label}选项无效。", 422)
        elif field.type == "number":
            try:
                number = Decimal(str(value))
            except (InvalidOperation, ValueError):
                raise BusinessError(f"{field.label}应为数字。", 422) from None
            if isinstance(value, bool) or not number.is_finite() or len(str(value)) > 40:
                raise BusinessError(f"{field.label}应为有限数字。", 422)
            value = str(number)
        elif field.type == "date":
            if not isinstance(value, str) or len(value) != 10:
                raise BusinessError(f"{field.label}日期无效。", 422)
            try:
                date.fromisoformat(value)
            except ValueError:
                raise BusinessError(f"{field.label}日期无效。", 422) from None
        elif not isinstance(value, str) or len(value) > 2000:
            raise BusinessError(f"{field.label}内容过长或格式无效。", 422)
        cleaned[field.name] = value
    return cleaned


def record_question_answer(interaction, request_key: str, answer: str, skipped: bool):
    if interaction.state != "waiting_for_user":
        raise BusinessError("此表单已提交，请刷新页面。", 409)
    submission = (
        {"skipped": True}
        if skipped
        else validate_values(interaction.definition, {"answer": answer})
    )
    interaction.submission = submission
    interaction.request_key = request_key
    interaction.state = "submitted"
    interaction.submitted_at = utcnow()
