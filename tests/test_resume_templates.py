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
        return render_template("workspace.html", conversations=[], count=0)


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
    assert html.count('class="rd-business-rule"') == 2
    assert html.count('class="rd-technical-nodes"') == 2
    assert html.count('class="rd-modern-layout"') == 2
    assert "墨绿商务抬头" in html
    assert "深蓝工程面板" in html
    assert "鼠尾草侧栏" in html
    assert "ENGINEERING / 技术项目" in html


def test_sample_and_account_photo_behavior_are_explicit(app):
    html = render_editor(app)
    assert "模板示例" in html
    assert "照片随简历保存到账号" in html
    assert "data-save-resume" in html
    assert "data-clear-sample" in html
    assert "data-print-resume" in html
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
