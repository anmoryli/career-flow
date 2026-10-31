"""Rendering, feature resources and cache versions share the page registry."""

import os
from pathlib import Path

from flask import g, render_template

from app.web.frontend import (
    PAGES_BY_TEMPLATE,
    WORKSPACE_PAGE_SPECS,
    WORKSPACE_PAGES,
    asset_fingerprint,
    page_assets,
    workspace_page,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_templates_and_shell_are_refactored():
    base = (ROOT / "app/templates/frontend/base.html").read_text(encoding="utf-8")
    for asset in ("css/app.css", "css/interface.css", "js/app.js", "js/career.js", "js/studio.js"):
        assert asset not in base
    assert "request.args" not in base
    assert "frontend_styles" in base and "frontend_scripts" in base
    assert "v='2026" not in base
    for template in WORKSPACE_PAGES.values():
        source = (ROOT / "app/templates" / template).read_text(encoding="utf-8")
        assert "extends 'frontend/base.html'" in source


def test_all_full_pages_have_registered_assets():
    templates = ROOT / "app/templates"
    pages = {
        path.relative_to(templates).as_posix()
        for path in (templates / "frontend").rglob("*.html")
        if "extends 'frontend/base.html'" in path.read_text(encoding="utf-8")
    } | {"frontend/resume/print.html"}
    assert pages == set(PAGES_BY_TEMPLATE)
    for page in PAGES_BY_TEMPLATE.values():
        styles, scripts = page_assets(page)
        for filename in styles + scripts:
            assert (ROOT / "app/static" / filename).is_file(), filename
        assert len(scripts) == len(set(scripts))
    _, scripts = page_assets(workspace_page("resume-new"))
    assert (
        scripts.index("js/frontend/resume-core.js")
        < scripts.index("js/frontend/resume-sort.js")
        < scripts.index("js/frontend/resume-editor.js")
    )
    assert "js/frontend/resume-templates.js" in page_assets(workspace_page("resume-template"))[1]


def test_unknown_workspace_view_and_guest_scope_stay_consistent():
    assert workspace_page("not-a-page") is workspace_page("dashboard")
    assert {view for view, page in WORKSPACE_PAGE_SPECS.items() if page.guest} == {
        "resume-new",
        "resume-template",
        "resume-import",
        "jobs",
    }


def test_assets_follow_rendered_template_instead_of_query(app):
    with app.test_request_context("/workspace?view=resume-new"):
        g.user = None
        html = render_template("frontend/public/error.html", message="测试错误", status=404)
        assert "css/frontend/public.css?v=" in html
        assert "js/frontend/resume-editor.js" not in html
        assert 'data-editor-page="no"' in html
        assert "20261031-drag-right" not in html
    versions = app.extensions["frontend_asset_versions"]
    assert all(len(version) == 16 for version in versions.values())
    assert versions["js/frontend/theme.js"] == asset_fingerprint(
        ROOT / "app/static/js/frontend/theme.js"
    )


def test_asset_version_tracks_bytes_even_with_preserved_mtime(tmp_path):
    asset = tmp_path / "asset.js"
    asset.write_bytes(b"first")
    stamp = asset.stat().st_mtime_ns
    first = asset_fingerprint(asset)
    assert first == asset_fingerprint(asset)
    asset.write_bytes(b"other")
    os.utime(asset, ns=(stamp, stamp))
    assert asset_fingerprint(asset) != first


def test_public_admin_and_export_use_new_templates():
    routes = (ROOT / "app/web/routes.py").read_text(encoding="utf-8")
    assert 'render_template("frontend/public/home.html")' in routes
    assert 'render_template("frontend/public/auth.html", mode="register")' in routes
    assert 'render_template("frontend/public/auth.html", mode="login")' in routes
    assert '"frontend/analysis/conversation.html"' in routes
    export = (ROOT / "app/web/career.py").read_text(encoding="utf-8")
    assert 'render_template("frontend/resume/print.html"' in export
    page = ROOT / "app/templates/frontend/resume/print.html"
    assert "css/app.css" not in page.read_text(encoding="utf-8")
    print_page = PAGES_BY_TEMPLATE["frontend/resume/print.html"]
    styles, scripts = page_assets(print_page)
    assert styles == tuple(
        f"css/frontend/{name}.css" for name in ("tokens", "components", "document", "resume")
    )
    assert scripts == ("js/frontend/resume-print.js",)
