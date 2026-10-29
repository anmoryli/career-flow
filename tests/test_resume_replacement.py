import pytest
from pydantic import ValidationError

from app.diagnosis_schemas import Suggestion
from app.resume_ai_schemas import ResumeAIOutput
from app.resume_text import ready_to_insert


@pytest.mark.parametrize("prefix", ["此外，", "另外，", "同时，", "建议写法：", "优化后：此外，"])
def test_ai_text_is_a_standalone_replacement(prefix):
    body = "设计接口并排查错误。"
    assert ready_to_insert(prefix + body) == body
    assert ResumeAIOutput(proposed=prefix + body, reason="改善表达").proposed == body
    assert (
        Suggestion(
            path="summary", original="接口开发", proposed=prefix + body, reason="改善表达"
        ).proposed
        == body
    )


def test_cleanup_does_not_modify_internal_sentence_or_accept_empty_copy():
    text = "负责此外项目的接口开发。"
    assert ready_to_insert(text) == text
    with pytest.raises(ValidationError):
        ResumeAIOutput(proposed="此外，", reason="空内容")
