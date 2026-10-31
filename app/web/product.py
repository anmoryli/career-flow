"""Non-payment product routes: safe exports, explicit shares, guides and measurement."""

import csv
import io
import json
from uuid import uuid4

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select

from app.admin_schemas import ConfigDraftInput
from app.extensions import db
from app.models import (
    AIOperation,
    Diagnostic,
    JobTarget,
    ReferralAttribution,
    ReferralCode,
    ReportShare,
    Resume,
)
from app.product_content import GUIDES
from app.product_schemas import AdoptionInput, ExportInput, ShareInput
from app.services import admin_config, career, product_growth
from app.services.errors import BusinessError
from app.services.product import (
    authorize_export,
    ensure_full_access,
    policy,
    record_event,
)
from app.web.admin import admin_required
from app.web.routes import input_data, login_required

product_web = Blueprint("product", __name__)


def private_response(template, **context):
    response = current_app.make_response(render_template(template, **context))
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@product_web.post("/api/resumes/<int:resume_id>/export")
@login_required
def export_resume(resume_id):
    data = ExportInput.model_validate(input_data())
    resume = career.owned(Resume, g.user.id, resume_id)
    version = career.version_of(resume, data.revision)
    authorize_export(g.user.id, version, consume=True)
    return {"url": url_for("career.print_resume", item_id=resume.id, revision=version.revision)}


@product_web.post("/api/resumes/<int:resume_id>/adoptions")
@login_required
def adoption(resume_id):
    data = AdoptionInput.model_validate(input_data())
    career.owned(Resume, g.user.id, resume_id)
    operation = career.owned(AIOperation, g.user.id, data.operation_id)
    if operation.resume_id != resume_id or operation.state != "succeeded":
        raise BusinessError("此建议不可采用。", 409)
    record_event(
        g.user.id,
        "ai_adopted",
        f"ai-adopted:{operation.id}",
        operation_id=operation.id,
        resume_id=resume_id,
        path=(operation.result or {}).get("path", "document"),
    )
    db.session.commit()
    return {"recorded": True}


@product_web.get("/jobs/<int:job_id>/report")
@login_required
def report(job_id):
    job = career.owned(JobTarget, g.user.id, job_id)
    diagnostic = db.session.scalar(select(Diagnostic).where(Diagnostic.job_id == job.id))
    operation = (
        db.session.scalar(
            select(AIOperation)
            .where(AIOperation.diagnostic_id == diagnostic.id, AIOperation.state == "succeeded")
            .order_by((AIOperation.kind == "report").desc(), AIOperation.id.desc())
        )
        if diagnostic
        else None
    )
    if operation is None:
        raise BusinessError("请先完成岗位分析。", 409)
    ensure_full_access(g.user.id, operation)
    return private_response("frontend/product/report.html", operation=operation, job=job)


@product_web.route("/operations/<int:operation_id>/share", methods=["GET", "POST"])
@login_required
def share_manage(operation_id):
    operation = career.owned(AIOperation, g.user.id, operation_id)
    form = {"request_key": str(uuid4()), "fields": ["scores", "gap_counts"], "days": 7}
    if request.method == "POST":
        form = {
            "request_key": request.form.get("request_key"),
            "fields": request.form.getlist("fields"),
            "days": request.form.get("days"),
        }
    data = ShareInput.model_validate(form | {"confirmed": "yes"})
    snapshot = product_growth.share_snapshot(operation, data.fields)
    if request.method == "POST" and request.form.get("action") == "create":
        if request.form.get("confirmed") != "yes":
            raise BusinessError("请先确认预览中的公开内容。", 422)
        share = product_growth.create_share(
            g.user.id, operation.id, data, request.form.get("preview_digest", "")
        )
        return redirect(
            url_for("product.share_manage", operation_id=operation.id, created=share.id), code=303
        )
    shares = db.session.scalars(
        select(ReportShare)
        .where(ReportShare.user_id == g.user.id, ReportShare.operation_id == operation.id)
        .order_by(ReportShare.created_at.desc())
    ).all()
    return private_response(
        "frontend/product/share_manage.html",
        operation=operation,
        share_form=data,
        preview=snapshot,
        preview_digest=product_growth.preview_signature(g.user.id, operation.id, data, snapshot),
        shares=shares,
        share_signature=product_growth.signature,
    )


@product_web.post("/shares/<identifier>/revoke")
@login_required
def revoke_share(identifier):
    item = product_growth.revoke_share(g.user.id, identifier)
    flash("分享已撤销，原链接立即失效。", "success")
    return redirect(url_for("product.share_manage", operation_id=item.operation_id), code=303)


@product_web.get("/s/<identifier>/<token>")
def public_share(identifier, token):
    item = product_growth.read_share(identifier, token)
    response = private_response(
        "frontend/product/share.html", snapshot=item.snapshot, expires_at=item.expires_at
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@product_web.get("/invite/<code>")
def invitation(code):
    item = db.session.scalar(select(ReferralCode).where(ReferralCode.code == code))
    if item is None:
        raise BusinessError("邀请链接不存在。", 404)
    if not g.user:
        session["referral_code"] = item.code
    return redirect(url_for("web.register" if not g.user else "web.workspace"), code=303)


@product_web.get("/invitations")
@login_required
def invitations():
    code = product_growth.invite_code(g.user.id)
    count = len(
        db.session.scalars(
            select(ReferralAttribution.new_user_id).where(
                ReferralAttribution.inviter_id == g.user.id
            )
        ).all()
    )
    return private_response(
        "frontend/product/invite.html",
        invite_url=url_for("product.invitation", code=code.code, _external=True),
        invited_count=count,
    )


@product_web.get("/guides")
def guides():
    return render_template(
        "frontend/product/guides.html",
        guides=GUIDES,
        canonical=url_for("product.guides", _external=True),
    )


@product_web.get("/guides/<slug>")
def guide(slug):
    if slug not in GUIDES:
        raise BusinessError("准备指南不存在。", 404)
    return render_template(
        "frontend/product/guide.html",
        guide=GUIDES[slug],
        slug=slug,
        guides=GUIDES,
        canonical=url_for("product.guide", slug=slug, _external=True),
    )


@product_web.get("/sitemap.xml")
def sitemap():
    from xml.sax.saxutils import escape

    links = [url_for("web.home", _external=True), url_for("product.guides", _external=True)] + [
        url_for("product.guide", slug=slug, _external=True) for slug in GUIDES
    ]
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join("<url><loc>" + escape(link) + "</loc></url>" for link in links)
        + "</urlset>",
        mimetype="application/xml",
    )


@product_web.get("/robots.txt")
def robots():
    return Response(
        "User-agent: *\nAllow: /\nDisallow: /workspace\nDisallow: /api/\n"
        "Disallow: /admin\nDisallow: /jobs/\nDisallow: /resumes/\nDisallow: /s/\n"
        "Disallow: /operations/\nDisallow: /invitations\nDisallow: /invite/\nSitemap: "
        + url_for("product.sitemap", _external=True)
        + "\n",
        mimetype="text/plain",
    )


@product_web.route("/admin/product", methods=["GET", "POST"])
@admin_required
def administration():
    from app.product_schemas import ProductPolicy
    from app.services.product_metrics import metrics

    if request.method == "POST":
        settings = ProductPolicy.model_validate_json(request.form.get("settings", ""))
        draft = admin_config.create_draft(
            g.user.id,
            "product",
            ConfigDraftInput(
                label=request.form.get("label", "产品权益规则"),
                settings=settings.model_dump(mode="json"),
            ),
        )
        flash(f"已保存草稿版本{draft.version}，发布后才对新任务生效。", "success")
        return redirect(url_for("product.administration"), code=303)
    config, _ = policy()
    history = admin_config.history("product")
    return private_response(
        "frontend/product/admin.html",
        metrics=metrics(),
        settings_json=json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2),
        history=history,
    )


@product_web.post("/admin/product/<int:revision_id>/<action>")
@admin_required
def publish_policy(revision_id, action):
    if request.form.get("confirm") != "yes":
        raise BusinessError("请确认发布或回滚。", 422)
    if action == "publish":
        admin_config.publish(g.user.id, "product", revision_id, True)
    elif action == "rollback":
        admin_config.rollback(g.user.id, "product", revision_id, True)
    else:
        raise BusinessError("操作不存在。", 404)
    flash("产品规则已更新，新任务按发布版本执行。", "success")
    return redirect(url_for("product.administration"), code=303)


@product_web.get("/admin/product/metrics.csv")
@admin_required
def metrics_csv():
    from app.services.product_metrics import metrics

    days = request.args.get("days", 30, type=int)
    if not 1 <= days <= 365:
        raise BusinessError("统计窗口应为1至365天。", 422)
    values = metrics(days)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["metric", "value"])
    writer.writerows((key, "" if value is None else value) for key, value in values.items())
    response = Response("\ufeff" + out.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=careerflow-product-metrics.csv"
    response.headers["Cache-Control"] = "no-store"
    return response
