"""The V1 page registry owns templates, feature assets and shell metadata."""

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

from flask import before_render_template, url_for


@dataclass(frozen=True)
class FrontendPage:
    template: str
    styles: tuple[str, ...] = ()
    scripts: tuple[str, ...] = ()
    current_view: str = ""
    editor: bool = False
    admin: bool = False
    task_path: bool = False
    guest: bool = False
    standalone: bool = False


WORKSPACE_PAGE_SPECS = MappingProxyType(
    {
        view: replace(page, current_view=view)
        for view, page in {
            "dashboard": FrontendPage("frontend/dashboard.html", scripts=("landing",)),
            "resumes": FrontendPage(
                "frontend/resume/library.html",
                ("resume",),
                ("resume-core", "resume-library"),
                task_path=True,
            ),
            "resume-template": FrontendPage(
                "frontend/resume/templates.html",
                ("resume",),
                ("resume-core", "resume-templates"),
                task_path=True,
                guest=True,
            ),
            "resume-new": FrontendPage(
                "frontend/resume/editor.html",
                ("resume",),
                ("resume-core", "resume-sort", "resume-editor"),
                editor=True,
                guest=True,
            ),
            "resume-import": FrontendPage(
                "frontend/resume/import_upload.html",
                ("resume",),
                ("resume-core", "resume-import"),
                task_path=True,
                guest=True,
            ),
            "optimize": FrontendPage(
                "frontend/resume/optimize.html",
                ("resume",),
                ("resume-core", "resume-library"),
                task_path=True,
            ),
            "jobs": FrontendPage(
                "frontend/analysis/jobs.html",
                ("analysis",),
                ("analysis", "analysis_review"),
                task_path=True,
                guest=True,
            ),
            "reports": FrontendPage(
                "frontend/analysis/reports.html",
                ("analysis",),
                ("analysis", "analysis_review"),
                task_path=True,
            ),
            "history": FrontendPage(
                "frontend/analysis/history.html",
                ("analysis",),
                ("analysis", "analysis_review"),
                task_path=True,
            ),
            "billing": FrontendPage("frontend/account/billing.html", ("account",)),
            "settings": FrontendPage("frontend/account/settings.html", ("account",)),
        }.items()
    }
)
WORKSPACE_PAGES = MappingProxyType(
    {view: page.template for view, page in WORKSPACE_PAGE_SPECS.items()}
)
PAGES_BY_TEMPLATE = MappingProxyType(
    {
        **{page.template: page for page in WORKSPACE_PAGE_SPECS.values()},
        **{
            f"frontend/public/{name}.html": FrontendPage(
                f"frontend/public/{name}.html", ("public",), ("landing",) if name == "home" else ()
            )
            for name in ("home", "auth", "password_reset", "error")
        },
        **{
            f"frontend/admin/{name}.html": FrontendPage(
                f"frontend/admin/{name}.html", ("admin",), ("admin",), admin=True
            )
            for name in ("dashboard", "users", "orders", "settings", "audit")
        },
        "frontend/resume/import_review.html": FrontendPage(
            "frontend/resume/import_review.html",
            ("resume",),
            ("resume-core", "resume-import"),
            current_view="resumes",
            task_path=True,
        ),
        **{
            f"frontend/analysis/{name}.html": FrontendPage(
                f"frontend/analysis/{name}.html",
                ("analysis",),
                ("analysis", "analysis_review"),
                current_view="history" if name == "conversation" else "jobs",
                task_path=True,
            )
            for name in ("detail", "review", "conversation")
        },
        "frontend/resume/print.html": FrontendPage(
            "frontend/resume/print.html",
            ("tokens", "components", "document", "resume"),
            ("resume-print",),
            standalone=True,
        ),
    }
)
COMMON_STYLES = ("utilities", "tokens", "components", "shell", "document", "landing")
COMMON_SCRIPTS = tuple(
    f"js/frontend/{name}.js" for name in ("runtime", "auth", "select", "craft")
) + ("vendor/htmx.min.js", "vendor/alpine.min.js")


def workspace_page(view):
    return WORKSPACE_PAGE_SPECS.get(view, WORKSPACE_PAGE_SPECS["dashboard"])


def workspace_template(view):
    return workspace_page(view).template


def page_assets(page):
    styles = page.styles if page.standalone else COMMON_STYLES + page.styles + ("craft",)
    scripts = tuple(f"js/frontend/{name}.js" for name in page.scripts)
    return tuple(
        f"css/frontend/{name}.css" for name in styles
    ), scripts if page.standalone else COMMON_SCRIPTS + scripts


def asset_fingerprint(path):
    return sha256(Path(path).read_bytes()).hexdigest()[:16]


def register_frontend_assets(app):
    # Compute once per application/deployment, independently of file modification times.
    paths = {"js/frontend/theme.js"}
    for page in PAGES_BY_TEMPLATE.values():
        styles, scripts = page_assets(page)
        paths.update(styles)
        paths.update(scripts)
    versions = {path: asset_fingerprint(Path(app.static_folder) / path) for path in paths}
    app.extensions["frontend_asset_versions"] = MappingProxyType(versions)
    app.jinja_env.globals["frontend_asset_url"] = lambda path: url_for(
        "static", filename=path, v=versions[path]
    )

    def prepare_page(_sender, template, context, **_extra):
        if not template.name or not template.name.startswith("frontend/"):
            return
        page = PAGES_BY_TEMPLATE[template.name]
        styles, scripts = page_assets(page)
        context.update(frontend_page=page, frontend_styles=styles, frontend_scripts=scripts)

    before_render_template.connect(prepare_page, sender=app, weak=False)


def register_evidence_filter(app):
    from app.services.diagnosis_evidence import evidence_rows, resume_passages

    app.jinja_env.filters["evidence_rows"] = evidence_rows
    app.jinja_env.filters["resume_passages"] = resume_passages
    register_frontend_assets(app)
