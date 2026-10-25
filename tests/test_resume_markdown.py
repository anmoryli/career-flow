from flask import render_template_string

from app.services.resume_markdown import resume_markdown


def test_safe_resume_markdown_subset():
    result = str(resume_markdown("**重点** 与 *补充*\n- 第一项\n- <script>alert(1)</script>"))
    assert "<strong>重点</strong>" in result
    assert "<em>补充</em>" in result
    assert "<ul><li>第一项</li>" in result
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result
    assert "<script>" not in result


def test_resume_markdown_is_registered_for_print_templates(app):
    with app.app_context():
        html = render_template_string("{{ text|resume_markdown }}", text="**成果** <img src=x>")
    assert "<strong>成果</strong>" in html
    assert "&lt;img src=x&gt;" in html
