"""Validated requests and output for a single resume text rewrite."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from app.career_schemas import (
    CustomSection,
    Education,
    Experience,
    Project,
    ResumeDocument,
    Skill,
)
from app.resume_text import ready_to_insert
from app.schemas import Input

RewriteMode = Literal["optimize", "expand", "generate", "professional", "concise"]


class ResumeAIQuote(Input):
    request_key: UUID
    revision: int = Field(gt=0)
    source_facts: str = Field(default="", max_length=2000)
    requirement: str = Field(default="", max_length=1000)
    mode: RewriteMode
    path: str = Field(
        pattern=r"^(summary|experiences\.[0-9]{1,2}\.bullets\.[0-9]{1,2}|projects\.[0-9]{1,2}\.description|education\.[0-9]{1,2}\.detail|custom_sections\.[0-9]\.content)$"
    )


class ResumeAIOutput(Input):
    proposed: str = Field(min_length=1, max_length=3000)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("proposed")
    @classmethod
    def replacement_text(cls, value):
        return ready_to_insert(value)


class ResumeComposeQuote(Input):
    request_key: UUID
    revision: int = Field(gt=0)
    source: str = Field(min_length=20, max_length=12000)


class ResumeComposeDocument(Input):
    """Content fields only: layout switches stay with the renderer, not the model.

    Real providers tried to fill ``section_order`` with their own key list and
    failed the whole draft, so the draft contract no longer exposes it.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    name: str = Field(default="", max_length=80)
    role: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=120)
    city: str = Field(default="", max_length=60)
    website: str = Field(default="", max_length=160)
    github: str = Field(default="", max_length=160)
    linkedin: str = Field(default="", max_length=160)
    summary: Annotated[str, StringConstraints(max_length=600)] = ""
    experiences: list[Experience] = Field(default_factory=list, max_length=20)
    projects: list[Project] = Field(default_factory=list, max_length=20)
    education: list[Education] = Field(default_factory=list, max_length=10)
    skills: list[Skill] = Field(default_factory=list, max_length=20)
    certificates: list[str] = Field(default_factory=list, max_length=30)
    languages: list[str] = Field(default_factory=list, max_length=20)
    custom_sections: list[CustomSection] = Field(default_factory=list, max_length=10)

    def complete(self) -> ResumeDocument:
        return ResumeDocument(**self.model_dump())


class ResumeComposeOutput(Input):
    document: ResumeComposeDocument
    reason: str = Field(min_length=1, max_length=500)
