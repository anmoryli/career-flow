"""Page ownership and the render map for the V1 frontend.

Legacy templates remain on disk to preserve unrelated work; live routes select
only this tree. Service APIs and business rules are unchanged.
"""
WORKSPACE_PAGES = {
    "dashboard": "frontend/dashboard.html",
    "resumes": "frontend/resume/library.html",
    "resume-template": "frontend/resume/templates.html",
    "resume-new": "frontend/resume/editor.html",
    "resume-import": "frontend/resume/import_upload.html",
    "optimize": "frontend/resume/optimize.html",
    "jobs": "frontend/analysis/jobs.html",
    "reports": "frontend/analysis/reports.html",
    "history": "frontend/analysis/history.html",
    "billing": "frontend/account/billing.html",
    "settings": "frontend/account/settings.html",
}


def workspace_template(view):
    return WORKSPACE_PAGES.get(view, WORKSPACE_PAGES["dashboard"])
