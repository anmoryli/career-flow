"""Validated resume documents; incomplete drafts are intentionally supported."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas import Input


class Experience(Input):
    company: str = Field(default="", max_length=120)
    role: str = Field(default="", max_length=120)
    period: str = Field(default="", max_length=60)
    location: str = Field(default="", max_length=60)
    bullets: list[str] = Field(default_factory=list, max_length=30)


class Project(Input):
    name: str = Field(default="", max_length=120)
    role: str = Field(default="", max_length=80)
    period: str = Field(default="", max_length=60)
    tech: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=2000)
    link: str = Field(default="", max_length=200)


class Education(Input):
    school: str = Field(default="", max_length=120)
    degree: str = Field(default="", max_length=120)
    period: str = Field(default="", max_length=60)
    detail: str = Field(default="", max_length=160)


class Skill(Input):
    label: str = Field(default="", max_length=40)
    items: list[str] = Field(default_factory=list, max_length=40)


class ResumeDocument(Input):
    name: str = Field(default="", max_length=80)
    role: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=120)
    city: str = Field(default="", max_length=60)
    website: str = Field(default="", max_length=160)
    github: str = Field(default="", max_length=160)
    linkedin: str = Field(default="", max_length=160)
    summary: str = Field(default="", max_length=600)
    experiences: list[Experience] = Field(default_factory=list, max_length=20)
    projects: list[Project] = Field(default_factory=list, max_length=20)
    education: list[Education] = Field(default_factory=list, max_length=10)
    skills: list[Skill] = Field(default_factory=list, max_length=20)
    certificates: list[str] = Field(default_factory=list, max_length=30)
    languages: list[str] = Field(default_factory=list, max_length=20)
    photo: str = Field(default="", max_length=3500000)
    hidden_sections: list[
        Literal[
            "summary", "experiences", "projects", "education", "skills", "certificates", "languages"
        ]
    ] = Field(default_factory=list, max_length=7)
    section_order: list[
        Literal[
            "summary", "experiences", "projects", "education", "skills", "certificates", "languages"
        ]
    ] = Field(
        default_factory=lambda: [
            "summary",
            "experiences",
            "projects",
            "education",
            "skills",
            "certificates",
            "languages",
        ],
        min_length=7,
        max_length=7,
    )
    size: Literal["compact", "standard", "large"] = "standard"
    accent: Literal["default", "green", "navy", "graphite"] = "default"
    photo_position: Literal["center", "top", "bottom"] = "center"

    @field_validator("section_order")
    @classmethod
    def unique_sections(cls, value: list[str]) -> list[str]:
        if len(set(value)) != 7:
            raise ValueError("板块顺序必须包含全部七个不同板块")
        return value


class ResumeSave(Input):
    request_key: UUID
    revision: int = Field(default=0, ge=0)
    title: str = Field(default="未命名简历", min_length=1, max_length=120)
    template: Literal["classic", "technical", "modern"] = "classic"
    document: ResumeDocument


class JobSave(Input):
    request_key: UUID
    resume_id: int = Field(gt=0)
    resume_revision: int = Field(gt=0)
    title: str = Field(default="", max_length=160)
    company: str = Field(default="", max_length=160)
    description: str = Field(min_length=1, max_length=20000)
    url: str = Field(default="", max_length=1000)


class CopyResume(Input):
    request_key: UUID
    title: str = Field(min_length=1, max_length=120)


class ConfirmDelete(Input):
    confirm: Literal["delete"]
