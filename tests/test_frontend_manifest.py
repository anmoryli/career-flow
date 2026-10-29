"""The live render map must not drift back to the retired frontend stack."""
from pathlib import Path

from app.web.frontend import WORKSPACE_PAGES

ROOT = Path(__file__).resolve().parents[1]


def test_live_templates_and_shell_are_refactored():
    base = (ROOT / "app/templates/frontend/base.html").read_text(encoding="utf-8")
    for asset in ("css/app.css", "css/interface.css", "js/app.js", "js/career.js", "js/studio.js"):
        assert asset not in base
    for template in WORKSPACE_PAGES.values():
        source = (ROOT / "app/templates" / template).read_text(encoding="utf-8")
        assert "extends 'frontend/base.html'" in source
    assert "js/frontend/runtime.js" in base
    assert "resume-templates.js" in base


def test_public_admin_and_export_use_new_templates():
    routes = (ROOT / "app/web/routes.py").read_text(encoding="utf-8")
    assert 'render_template("frontend/public/home.html")' in routes
    assert 'render_template("frontend/public/auth.html", mode="login")' in routes
    assert '"frontend/analysis/conversation.html"' in routes
    export = (ROOT / "app/web/career.py").read_text(encoding="utf-8")
    assert 'render_template("frontend/resume/print.html"' in export
    page = ROOT / "app/templates/frontend/resume/print.html"
    assert "css/app.css" not in page.read_text(encoding="utf-8")
