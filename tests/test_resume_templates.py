import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flask import g, render_template
from pydantic import ValidationError

from app.career_schemas import ResumeDocument

ROOT = Path(__file__).resolve().parents[1]


def editor_js():
    return (ROOT / "app/static/js/frontend/resume-editor.js").read_text(encoding="utf-8")


def render_editor(app):
    with app.test_request_context("/workspace?view=resume-new"):
        g.user = SimpleNamespace(
            id=uuid4(),
            display_name="模板测试",
            email="template@example.com",
            theme="system",
            created_at=datetime(2026, 10, 22),
        )
        return render_template(
            "frontend/resume/editor.html",
            conversations=[],
            count=0,
            resumes=[],
            jobs=[],
            saved_jobs=[],
            active_jobs=[],
            active_job_ids=set(),
            inactive_saved_jobs=[],
            recent_only_jobs=[],
            current_resume=None,
            resume_previews={},
            reports=[],
            completed_reports=[],
            entitlements=SimpleNamespace(
                can_create_resume=True,
                resume_count=0,
                resume_limit=10,
                can_export_resume=True,
            ),
            membership=None,
            orders=[],
            commerce_plans=None,
            mock_payment_enabled=False,
            uuid4=uuid4,
            now=datetime(2026, 11, 2),
        )


def test_every_template_renders_a_visible_photo_slot(app):
    html = render_editor(app)
    # Every picker thumbnail shares the same photo macro: one slot (with an
    # empty-state placeholder) per rendered document, no exceptions.
    documents = html.count("data-resume-doc=")
    assert documents == 20
    assert html.count("data-photo-slot") == documents
    assert html.count("data-photo-placeholder") == documents
    assert html.count("data-rf-photo") == documents
    js = editor_js()
    # The photo editor itself is generated client-side; keep its contract intact.
    assert "resume-photo" in js
    assert "上传个人照片" in js
    assert "removePhoto" in js
    assert "resume-photo-position" in js
    assert 'id="resume-template-quick"' in html


def test_three_templates_have_distinct_visual_structures(app):
    html = render_editor(app)
    # classic keeps the linear head; technical and modern moved to split rails.
    assert html.count('class="rd-head rd-head-classic"') >= 2
    assert html.count('data-layout="linear"') >= 2
    assert html.count('data-layout="split"') >= 2
    assert "rd-split-rail" in html
    assert "rd-skills-pills" in html

def test_sample_and_account_photo_behavior_are_explicit(app):
    html = render_editor(app)
    # The draft preview is the default; the rich example only lives in the
    # preview channel and never leaks into the form.
    assert 'data-preview-mode="draft"' in html
    assert "data-example=" in html
    assert "data-examples=" in html
    js = editor_js()
    assert "示例内容不会写入你的简历" in js
    assert "照片会随简历保存到账号" in js
    assert "data-save-resume" in html
    # Export stays available on the editor; the print flow lives in its own page.
    assert "data-print-resume" in html


def test_summary_section_and_input_have_unique_ids(app):
    js = editor_js()
    assert js.count("'resume-summary'") == 1
    assert js.count("'resume-summary-section'") == 1


def test_section_order_requires_each_resume_section_once():
    document = ResumeDocument()
    assert len(document.section_order) == 7
    with pytest.raises(ValidationError):
        ResumeDocument(section_order=["summary"] * 7)


def test_unfilled_resume_defaults_are_removed_before_save():
    empty_custom_id = "00000000-0000-4000-8000-000000000001"
    content_custom_id = "00000000-0000-4000-8000-000000000002"
    document = ResumeDocument(
        name=" 林澄 ",
        experiences=[{}, {"company": " 示例公司 ", "bullets": ["", " 做过的工作 "]}],
        projects=[{}],
        education=[{}],
        skills=[{"label": "核心能力", "items": []}, {"items": [" Python ", ""]}],
        certificates=["", " PMP "] ,
        languages=["   "],
        custom_sections=[
            {"id": empty_custom_id, "title": "自定义板块", "content": ""},
            {"id": content_custom_id, "title": "", "content": "补充经历"},
        ],
        section_order=[
            "summary", "experiences", "projects", "education", "skills",
            "certificates", "languages", f"custom:{empty_custom_id}",
            f"custom:{content_custom_id}",
        ],
        hidden_sections=[f"custom:{empty_custom_id}"],
    )
    assert document.name == "林澄"
    assert [item.company for item in document.experiences] == ["示例公司"]
    assert document.experiences[0].bullets == ["做过的工作"]
    assert document.projects == []
    assert document.education == []
    assert [(group.label, group.items) for group in document.skills] == [("", ["Python"])]
    assert document.certificates == ["PMP"]
    assert document.languages == []
    assert len(document.custom_sections) == 1
    assert document.custom_sections[0].title == ""
    assert document.custom_sections[0].content.strip()
    assert document.section_order[-1] == f"custom:{content_custom_id}"
    assert document.hidden_sections == []


class EditorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = []
        self.textarea = None
        self.example = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-example" in attrs:
            self.example = json.loads(attrs["data-example"])
        if "data-rf-field" in attrs:
            self.fields.append(attrs)
            if tag == "textarea":
                self.textarea = attrs

    def handle_data(self, data):
        if self.textarea is not None:
            self.textarea["value"] = self.textarea.get("value", "") + data

    def handle_endtag(self, tag):
        if tag == "textarea":
            self.textarea = None


def test_editor_starts_empty_with_placeholders(app):
    html = render_editor(app)
    # All editable fields are generated client-side from an empty document;
    # the server never renders prefilled inputs or example values.
    assert "data-rf-field" not in html
    assert 'value="示例' not in html
    # Example content is only reachable through the preview channel.
    assert "data-example=" in html


def test_rich_example_is_separate_from_form(app):
    html = render_editor(app)
    match = re.search(r"data-example='([^']+)'", html)
    assert match, "editor must embed the sample document for the preview"
    example = json.loads(match.group(1))
    assert len(example["experiences"]) == 2
    assert len(example["projects"]) == 2
    assert len(example["skills"]) == 4
    assert len(example["certificates"]) == 2
    assert all(len(item["bullets"]) >= 2 for item in example["experiences"])
