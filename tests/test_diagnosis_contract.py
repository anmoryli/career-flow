import pytest
from pydantic import ValidationError

from app.diagnosis_schemas import DiagnosisOutput
from app.services.model_provider import INSTRUCTIONS
from app.services.model_runtime import AI_PROVIDER_BILLING_MESSAGE, public_ai_error
from tests.integration.test_career import valid_output


def test_prompt_explicitly_requires_each_canonical_dimension():
    for name in ("技能匹配", "岗位职责", "工作与项目经历", "成果与影响力", "学历及其他条件"):
        assert name in INSTRUCTIONS
    data = valid_output({})
    data["dimensions"][0]["name"] = "产品管理"
    with pytest.raises(ValidationError):
        DiagnosisOutput.model_validate(data)


def test_provider_billing_message_is_separate_from_membership_and_maps_history(app):
    from flask import render_template_string

    for message in (
        "模型服务账户余额不足或未开通此模型，请检查服务商账户。",
        "模型服务余额不足，请稍后重试。",
    ):
        assert public_ai_error(message) == AI_PROVIDER_BILLING_MESSAGE
        with app.app_context():
            assert render_template_string("{{ error|ai_public_error }}", error=message) == (
                AI_PROVIDER_BILLING_MESSAGE
            )
    assert public_ai_error("输入无效") == "输入无效"
    assert public_ai_error(None) == ""
