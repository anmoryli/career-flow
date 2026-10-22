from datetime import datetime
from types import SimpleNamespace

from flask import g, render_template


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


def test_sample_and_local_photo_limitations_are_explicit(app):
    html = render_editor(app)
    assert "当前展示的是示例内容" in html
    assert "暂不保存到账号" in html
    assert "data-clear-sample" in html
    assert "data-print-resume" in html
    assert 'data-resume-panel="classic"' in html
    assert 'data-resume-panel="technical" hidden' in html
    assert 'data-resume-panel="modern" hidden' in html


def test_summary_section_and_input_have_unique_ids(app):
    html = render_editor(app)
    assert html.count('id="resume-summary"') == 1
    assert html.count('id="resume-summary-section"') == 1
