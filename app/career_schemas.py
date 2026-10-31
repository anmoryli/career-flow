"""Validated resume documents; incomplete drafts are intentionally supported."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.resume_templates import TemplateId
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


class CustomSection(Input):
    id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    title: str = Field(default="", max_length=80)
    content: str = Field(default="", max_length=4000)


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
    custom_sections: list[CustomSection] = Field(default_factory=list, max_length=10)
    photo: str = Field(default="", max_length=3500000)
    hidden_sections: list[str] = Field(default_factory=list, max_length=17)
    section_order: list[str] = Field(
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
        max_length=17,
    )
    size: Literal["compact", "standard", "large"] = "standard"
    accent: Literal["default", "green", "navy", "graphite"] = "default"
    photo_position: Literal["center", "top", "bottom"] = "center"

    @model_validator(mode="after")
    def discard_unfilled_fields(self):
        for field in (
            "name", "role", "phone", "email", "city", "website", "github",
            "linkedin", "summary",
        ):
            setattr(self, field, getattr(self, field).strip())
        for field in ("website", "github", "linkedin"):
            if getattr(self, field).lower() in {"http://", "https://"}:
                setattr(self, field, "")

        for item in self.experiences:
            for field in ("company", "role", "period", "location"):
                setattr(item, field, getattr(item, field).strip())
            item.bullets = [line.strip() for line in item.bullets if line.strip()]
        self.experiences = [
            item for item in self.experiences
            if any((item.company, item.role, item.period, item.location, *item.bullets))
        ]

        for item in self.projects:
            for field in ("name", "role", "period", "tech", "description", "link"):
                setattr(item, field, getattr(item, field).strip())
            if item.link.lower() in {"http://", "https://"}:
                item.link = ""
        self.projects = [
            item for item in self.projects
            if any((item.name, item.role, item.period, item.tech, item.description, item.link))
        ]

        for item in self.education:
            for field in ("school", "degree", "period", "detail"):
                setattr(item, field, getattr(item, field).strip())
        self.education = [
            item for item in self.education
            if any((item.school, item.degree, item.period, item.detail))
        ]

        for item in self.skills:
            item.label = item.label.strip()
            item.items = [skill.strip() for skill in item.items if skill.strip()]
        self.skills = [item for item in self.skills if item.items]
        self.certificates = [item.strip() for item in self.certificates if item.strip()]
        self.languages = [item.strip() for item in self.languages if item.strip()]

        for item in self.custom_sections:
            item.title = item.title.strip()
            item.content = item.content.strip()
        valid_custom = {item.id for item in self.custom_sections if item.content}
        self.custom_sections = [item for item in self.custom_sections if item.content]
        valid_order = {
            "summary", "experiences", "projects", "education", "skills",
            "certificates", "languages",
            *(f"custom:{section_id}" for section_id in valid_custom),
        }
        self.section_order = [key for key in self.section_order if key in valid_order]
        self.hidden_sections = [key for key in self.hidden_sections if key in valid_order]
        return self

    @model_validator(mode="after")
    def valid_section_layout(self):
        built_in = {
            "summary", "experiences", "projects", "education", "skills", "certificates", "languages"
        }
        custom = {f"custom:{section.id}" for section in self.custom_sections}
        expected = built_in | custom
        if len(custom) != len(self.custom_sections):
            raise ValueError("自定义板块编号不能重复")
        if len(self.section_order) != len(expected) or set(self.section_order) != expected:
            raise ValueError("板块顺序必须包含所有简历板块")
        if (
            len(set(self.hidden_sections)) != len(self.hidden_sections)
            or not set(self.hidden_sections) <= expected
        ):
            raise ValueError("隐藏板块必须来自当前简历")
        return self


class ResumeSave(Input):
    request_key: UUID
    revision: int = Field(default=0, ge=0)
    title: str = Field(default="未命名简历", min_length=1, max_length=120)
    template: TemplateId = "classic"
    document: ResumeDocument


class JobSave(Input):
    request_key: UUID
    resume_id: int = Field(gt=0)
    resume_revision: int = Field(gt=0)
    title: str = Field(default="", max_length=160)
    company: str = Field(default="", max_length=160)
    description: str = Field(min_length=1, max_length=20000)
    url: str = Field(default="", max_length=1000)
    save_for_later: bool = True


class CopyResume(Input):
    request_key: UUID
    title: str = Field(min_length=1, max_length=120)


class ConfirmDelete(Input):
    confirm: Literal["delete"]
