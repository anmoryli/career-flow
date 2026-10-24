from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import StructuredMessage
from app.services.errors import BusinessError
from app.services.interactions import validate_values


def definition(fields):
    return {
        "schema_version": "1.0",
        "message": "请核对",
        "blocks": [{"type": "form", "id": str(uuid4()), "fields": fields}],
        "conversation_state": "waiting_for_user",
    }


def test_structured_form_rejects_unsupported_and_duplicate_fields():
    base = {"name": "city", "label": "城市", "type": "text"}
    with pytest.raises(ValidationError):
        StructuredMessage.model_validate(definition([base, base]))
    with pytest.raises(ValidationError):
        StructuredMessage.model_validate(definition([base | {"type": "html"}]))
    with pytest.raises(ValidationError):
        StructuredMessage.model_validate(definition([base | {"type": "select"}]))


def test_form_submission_validates_type_options_required_and_extra():
    form = definition(
        [
            {"name": "city", "label": "城市", "type": "text", "required": True},
            {
                "name": "mode",
                "label": "方式",
                "type": "radio",
                "options": ["远程", "到岗"],
            },
            {"name": "date", "label": "日期", "type": "date"},
            {"name": "years", "label": "年限", "type": "number"},
            {"name": "agree", "label": "确认", "type": "checkbox"},
        ]
    )
    assert validate_values(
        form,
        {"city": "上海", "mode": "远程", "date": "2026-10-24", "years": 3, "agree": True},
    ) == {"city": "上海", "mode": "远程", "date": "2026-10-24", "years": "3", "agree": True}
    for bad in (
        {},
        {"city": "上海", "mode": "虚构选项"},
        {"city": "上海", "date": "2026-02-30"},
        {"city": "上海", "years": "NaN"},
        {"city": "上海", "agree": "true"},
        {"city": "上海", "javascript": "alert(1)"},
    ):
        with pytest.raises(BusinessError):
            validate_values(form, bad)
