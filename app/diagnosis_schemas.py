from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas import Input


class QuoteInput(Input):
    request_key: UUID
    kind: Literal["analysis", "report"]


class AnswerInput(Input):
    request_key: UUID
    revision: int = Field(ge=0)
    answer: str = Field(default="", max_length=2000)
    skipped: bool = False

    @model_validator(mode="after")
    def content_required(self):
        if not self.skipped and not self.answer:
            raise ValueError("请填写回答或选择跳过")
        return self


class Finding(Input):
    requirement: str = Field(min_length=1, max_length=1000)
    category: Literal["hard", "bonus", "missing"]
    evidence: str = Field(max_length=2000)
    source: Literal["resume", "answer", "none"]
    explanation: str = Field(min_length=1, max_length=2000)


class Dimension(Input):
    name: Literal["技能匹配", "岗位职责", "工作与项目经历", "成果与影响力", "学历及其他条件"]
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=2000)


class Suggestion(Input):
    path: str = Field(
        pattern=r"^(summary|experiences\.[0-9]{1,2}\.bullets\.[0-9]{1,2}|projects\.[0-9]{1,2}\.description)$"
    )
    original: str = Field(min_length=1, max_length=3000)
    proposed: str = Field(min_length=1, max_length=3000)
    reason: str = Field(min_length=1, max_length=2000)


class DiagnosisOutput(Input):
    summary: str = Field(min_length=1, max_length=3000)
    dimensions: list[Dimension] = Field(min_length=5, max_length=5)
    findings: list[Finding] = Field(min_length=1, max_length=40)
    suggestions: list[Suggestion] = Field(default_factory=list, max_length=30)
    question: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def unique_dimensions(self):
        if len({item.name for item in self.dimensions}) != 5:
            raise ValueError("五个维度必须各出现一次")
        return self


class ApplySuggestion(Input):
    request_key: UUID
    indices: list[int] = Field(min_length=1, max_length=30)
    confirmed: Literal["yes"]
    title: str = Field(min_length=1, max_length=120)
    edits: dict[int, Annotated[str, Field(min_length=1, max_length=3000)]] = Field(
        default_factory=dict, max_length=30
    )


class DiagnosisResult(DiagnosisOutput):
    """Stored result adds a server-calculated score to the provider output contract."""

    overall_score: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def consistent_total(self):
        if self.overall_score != sum(item.score for item in self.dimensions) / 5:
            raise ValueError("总分必须由五维等权计算")
        return self
