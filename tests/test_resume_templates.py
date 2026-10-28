import json
from datetime import datetime
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from flask import g, render_template
from pydantic import ValidationError

from app.career_schemas import ResumeDocument


def render_editor(app):
    with app.test_request_context("/workspace?view=resume-new"):
        g.user = SimpleNamespace(
            display_name="模板测试",
            email="template@example.com",
            theme="system",
            created_at=datetime(2026, 10, 22),
        )
        return render_template(
            "workspace.html",
            conversations=[],
            count=0,
            entitlements={"can_create_resume": True, "resume_count": 0, "resume_limit": 10},
        )


def test_three_templates_have_visible_photo_slots(app):
    html = render_editor(app)
    # Three picker examples and three actual preview documents share the same macro.
    assert html.count('class="rd-photo-frame"') == 6
    assert html.count("data-photo-placeholder") == 6
    assert html.count("data-rf-photo") == 6
    assert html.count('id="resume-photo"') == 1
    assert "上传个人照片" in html
    assert "data-remove-photo" in html
    assert 'id="resume-photo-position"' in html
    assert 'id="resume-template-quick"' in html


def test_three_templates_have_distinct_visual_structures(app):
    html = render_editor(app)
    assert html.count('class="rd-head rd-head-classic"') == 2
    assert html.count('class="rd-head rd-head-technical"') == 2
    assert html.count('class="rd-modern-layout"') == 2
    assert "TECHNICAL RESUME" in html
    assert "CAREER PROFILE" in html

def test_sample_and_account_photo_behavior_are_explicit(app):
    html = render_editor(app)
    # Keep the sample labeled without exposing a long implementation-style disclaimer.
    assert "模板预览提供虚构示例" not in html
    assert html.count('class="template-sample-badge">示例</span>') == 3
    assert "照片随简历保存到账号" in html
    assert "data-save-resume" in html
    assert "data-clear-sample" in html
    assert "data-print-resume" not in html
    assert 'href="/workspace?view=billing"' in html
    assert 'data-resume-panel="classic"' in html
    assert 'data-resume-panel="technical" hidden' in html
    assert 'data-resume-panel="modern" hidden' in html


def test_summary_section_and_input_have_unique_ids(app):
    html = render_editor(app)
    assert html.count('id="resume-summary"') == 1
    assert html.count('id="resume-summary-section"') == 1


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
    parser = EditorParser()
    parser.feed(render_editor(app))
    assert len(parser.fields) == 45
    for field in parser.fields:
        assert not field.get("value", "").strip(), field["data-rf-field"]
        assert field.get("placeholder", "").strip(), field["data-rf-field"]


def test_rich_example_is_separate_from_form(app):
    html = render_editor(app)
    parser = EditorParser()
    parser.feed(html)
    assert 'id="resume-preview-mode"' in html
    assert 'data-preview-mode="sample"' in html
    assert len(parser.example["experiences"]) == 2
    assert len(parser.example["projects"]) == 2
    assert len(parser.example["skills"]) == 4
    assert len(parser.example["certificates"]) == 2
    assert all(len(item["bullets"]) >= 2 for item in parser.example["experiences"])
