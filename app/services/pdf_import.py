import base64
import hashlib
import io
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from sqlalchemy import select

from app.career_schemas import Education, Project, ResumeDocument, Skill
from app.extensions import db
from app.models import ResumeImport
from app.services.career import owned
from app.services.diagnosis import owner_lock
from app.services.errors import BusinessError


class PDFInputError(ValueError):
    pass


def tesseract_executable():
    """Prefer the project-local OCR runtime, with a system runtime as deployment fallback."""
    root = Path(__file__).resolve().parents[2]
    for filename in ("tesseract.exe", "tesseract"):
        bundled = root / ".tools" / "tesseract" / filename
        if bundled.is_file():
            return str(bundled)
    return shutil.which("tesseract")


def ocr_page(page, deadline):
    """Render one textless page and recognize it without writing a user file to disk."""
    if page.width <= 0 or page.height <= 0 or page.width * page.height > 5_000_000:
        raise PDFInputError("扫描页尺寸过大，无法安全识别。")
    resolution = min(180, int(72 * math.sqrt(5_000_000 / (page.width * page.height))))
    image = page.to_image(resolution=resolution).original
    with io.BytesIO() as stream:
        image.save(stream, format="PNG")
        image_bytes = stream.getvalue()
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PDFInputError("扫描件识别超时，请减少页数或上传文字版 PDF。")
    executable = tesseract_executable()
    if not executable:
        raise PDFInputError("OCR 服务未安装，请在项目依赖目录配置 Tesseract 或上传文字版 PDF。")
    args = [executable, "stdin", "stdout"]
    local_tessdata = Path(executable).resolve().parent / "tessdata"
    if local_tessdata.is_dir():
        args.extend(["--tessdata-dir", str(local_tessdata)])
    args.extend(["-l", "chi_sim+eng", "--psm", "3"])
    try:
        result = subprocess.run(
            args,
            input=image_bytes,
            capture_output=True,
            timeout=min(20, remaining),
            check=False,
            env=os.environ | {"OMP_THREAD_LIMIT": "1"},
        )
    except FileNotFoundError:
        raise PDFInputError("OCR 服务未安装，请联系管理员或上传文字版 PDF。") from None
    except subprocess.TimeoutExpired:
        raise PDFInputError("扫描件识别超时，请减少页数或上传文字版 PDF。") from None
    if result.returncode:
        raise PDFInputError("扫描件识别失败，请检查 OCR 中文语言包或上传文字版 PDF。")
    return result.stdout.decode("utf-8", errors="replace").strip()


def create_import(user_id, request_key, content):
    if not content.startswith(b"%PDF-"):
        raise BusinessError("请选择有效 PDF 文件。", 422)
    if len(content) > 4 * 1024 * 1024:
        raise BusinessError("PDF 不能超过 4 MB。", 413)
    owner_lock(user_id)
    digest = hashlib.sha256(content).hexdigest()
    item = db.session.scalar(
        select(ResumeImport)
        .where(ResumeImport.user_id == user_id, ResumeImport.request_key == str(request_key))
        .with_for_update()
    )
    if item:
        if item.digest != digest:
            raise BusinessError("重复导入请求内容不一致。", 409)
    else:
        item = ResumeImport(
            user_id=user_id,
            request_key=str(request_key),
            digest=digest,
            content=content,
            state="queued",
        )
        db.session.add(item)
    db.session.commit()
    return item


_DATE_RANGE = re.compile(
    r"(20\d{2}\s*[./年-]\s*\d{1,2}\s*月?)\s*(?:~|～|—|–|-|至)\s*"
    r"(至今|20\d{2}\s*[./年-]\s*\d{1,2}\s*月?)"
)
_BULLET = re.compile(r"^[\s\u2022\u25cf\u26ab\u25aa\u25e6\-]+")


def _normalise_pdf_line(line: str) -> str:
    line = re.sub(r"(?<=\d)\s+(?=\d)", "", line)
    return re.sub(r"\s+", " ", line).strip()


def _section_index(lines, pattern, default):
    return next((i for i, line in enumerate(lines) if re.search(pattern, line, re.I)), default)


def _resume_document_from_text(text: str) -> ResumeDocument:
    lines = [_normalise_pdf_line(line) for line in text.splitlines()]
    profile_text = "\n".join(lines)
    name_match = re.search(r"姓名\s*[:：]\s*([^\s|]+)", profile_text)
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", profile_text)
    phone_match = re.search(r"(?<!\d)1(?:[\s-]*\d){10}(?!\d)", profile_text)
    phone = re.sub(r"\D", "", phone_match.group()) if phone_match else ""

    def labelled_value(label):
        match = re.search(rf"(?:{label})\s*[:：]\s*([^\s|]+)", profile_text, re.I)
        value = match.group(1).rstrip("，,。；;") if match else ""
        return re.sub(r"^https?://", "", value, flags=re.I).rstrip("/")

    website = labelled_value("个人主页|主页|网站")
    github = labelled_value("github(?:账号|帐号)?")
    if not github:
        github_match = re.search(r"(?:https?://)?github\.com/[\w.-]+", profile_text, re.I)
        github = (
            re.sub(r"^https?://", "", github_match.group(0), flags=re.I)
            if github_match else ""
        )

    education_at = _section_index(lines, r"教育经历|Education", len(lines))
    projects_at = _section_index(lines, r"科研和项目经历|工作经历|项目经历|Experience", len(lines))
    skills_at = _section_index(lines, r"技术能力|专业技能|Skills", len(lines))
    skills_content_at = skills_at + 1
    if skills_at == len(lines):
        skill_tokens = re.compile(
            r"\b(?:Python|Java|JavaScript|TypeScript|C\+\+|C#|Go|Rust|MySQL|"
            r"PostgreSQL|Redis|MongoDB|React|Vue|Spring|Flask|FastAPI|Docker|"
            r"Kubernetes|Linux|Git|HTML|CSS|SQL)\b",
            re.I,
        )
        inferred_skill_lines = [
            index
            for index, line in enumerate(lines)
            if index > projects_at and len(skill_tokens.findall(line)) >= 2
        ]
        if inferred_skill_lines:
            skills_at = inferred_skill_lines[-1]
            skills_content_at = skills_at
    awards_at = _section_index(lines, r"荣誉奖项|获奖情况|Honor", len(lines))

    education = []
    education_lines = lines[education_at + 1 : projects_at]
    if education_at == len(lines):
        education_lines = [
            line
            for line in lines[:projects_at]
            if _DATE_RANGE.search(line)
            and re.search(r"大学|学院|学校|University|College", line, re.I)
        ]
    for line in education_lines:
        date_match = _DATE_RANGE.search(line)
        if not date_match:
            continue
        period = f"{date_match.group(1)} - {date_match.group(2)}"[:60]
        remainder = (line[: date_match.start()] + " " + line[date_match.end() :]).strip(" |·—-")
        school_match = re.search(
            r"^(.+?(?:大学|学院|学校|University|College))\s*(.*)$",
            remainder,
            re.I,
        )
        school = school_match.group(1).strip() if school_match else remainder[:120]
        details = school_match.group(2).strip() if school_match else ""
        degree_match = re.search(
            r"(博士研究生|硕士研究生|本科|专科|博士|硕士|学士|Associate|Bachelor|Master|PhD)",
            details,
            re.I,
        )
        degree = degree_match.group(1) if degree_match else ""
        major = details.replace(degree, "", 1).strip(" ·,，") if degree else details
        supporting = [
            _BULLET.sub("", item).strip()
            for item in education_lines
            if item != line and _BULLET.match(item) and _BULLET.sub("", item).strip()
        ]
        education.append(Education(
            school=school[:120], degree=degree[:120], period=period,
            detail=" · ".join(([major] if major else []) + supporting)[:160],
        ))
        break

    projects = []
    project_lines = lines[projects_at + 1 : skills_at]
    current = None
    tech_mode = False
    for line in project_lines:
        date_match = _DATE_RANGE.search(line)
        if date_match:
            if current:
                projects.append(current)
            header = line[: date_match.start()].strip(" |·—-")
            after = line[date_match.end() :].strip(" |·—-")
            parts = [part.strip() for part in header.split("|") if part.strip()]
            current = {
                "name": (parts[0] if parts else header)[:120],
                "role": (parts[1] if len(parts) > 1 else "")[:80],
                "period": f"{date_match.group(1)} - {date_match.group(2)}"[:60],
                "description": "；".join(parts[2:] + ([after] if after else [])),
                "tech": "",
                "bullets": [],
            }
            tech_mode = False
            continue
        if not current:
            continue
        if re.search(r"核心技术栈|技术栈", line):
            tech_mode = True
            continue
        if re.fullmatch(r"项目成果|个人成果", line):
            if current:
                projects.append(current)
            current = None
            break
        content = _BULLET.sub("", line).strip()
        if not content:
            continue
        if tech_mode:
            current["tech"] = (current["tech"] + "、" + content).strip("、")[:160]
        elif _BULLET.match(line):
            current["bullets"].append(content)
    if current:
        projects.append(current)
    structured_projects = [
        Project(
            name=item["name"], role=item["role"], period=item["period"], tech=item["tech"],
            description="\n".join(filter(None, [item["description"], *item["bullets"]]))[:2000],
        )
        for item in projects[:20]
    ]

    skills = []
    for line in lines[skills_content_at:awards_at]:
        content = _BULLET.sub("", line).strip()
        if not content or re.fullmatch(r"核心技术栈|技术栈", content):
            continue
        parts = re.split(r"[:：]", content, maxsplit=1)
        if len(parts) == 1:
            label, values = "技能", content
        else:
            label, values = parts
        items = [item.strip() for item in re.split(r"[、，,;；]", values) if item.strip()]
        if items:
            skills.append(Skill(label=label.strip()[:40], items=items[:40]))

    certificates = []
    for line in lines[awards_at + 1 :]:
        if not line:
            continue
        pieces = [
            piece.strip()
            for piece in re.split(r"[\u2022\u25cf\u26ab\u25aa\u25e6]+", line)
            if piece.strip()
        ]
        for piece in pieces:
            if not re.fullmatch(r"国家级荣誉|校级荣誉|算法与建模类奖项|荣誉", piece):
                certificates.append(piece[:160])

    document = ResumeDocument(
        name=name_match.group(1)[:80] if name_match else "",
        email=email_match.group(0)[:120] if email_match else "",
        phone=phone,
        website=website[:160],
        github=github[:160],
        education=education,
        projects=structured_projects,
        skills=skills[:20],
        certificates=list(dict.fromkeys(certificates))[:30],
    )
    return document


def _extract_resume_photo(pages) -> str:
    """Extract a standalone portrait image, ignoring scans and decorative banners."""
    from PIL import Image, ImageOps

    candidates = []
    for page in pages:
        page_area = max(1, page.width * page.height)
        for image in getattr(page, "images", []):
            box_width = max(0, image.get("x1", 0) - image.get("x0", 0))
            box_height = max(0, image.get("bottom", 0) - image.get("top", 0))
            ratio = box_width / box_height if box_height else 0
            area_ratio = (box_width * box_height) / page_area
            if not (0.55 <= ratio <= 1.15 and 0.004 <= area_ratio <= 0.20):
                continue
            stream = image.get("stream")
            if stream is None:
                continue
            try:
                raw = stream.get_data()
                with Image.open(io.BytesIO(raw)) as opened:
                    if (
                        opened.width < 96
                        or opened.height < 96
                        or opened.width * opened.height > 16_000_000
                    ):
                        continue
                    if not (0.55 <= opened.width / opened.height <= 1.15):
                        continue
                    opened.verify()
                with Image.open(io.BytesIO(raw)) as opened:
                    photo = ImageOps.exif_transpose(opened).convert("RGB")
                    photo.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                    output = io.BytesIO()
                    photo.save(output, format="JPEG", quality=88, optimize=True)
                    encoded = base64.b64encode(output.getvalue()).decode("ascii")
                score = area_ratio - abs(ratio - 0.78) * 0.001
                candidates.append((score, f"data:image/jpeg;base64,{encoded}"))
            except (OSError, ValueError, Image.DecompressionBombError):
                continue
    return max(candidates, key=lambda candidate: candidate[0])[1] if candidates else ""


def parse_pdf(content):
    import pdfplumber

    deadline = time.monotonic() + 90
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) > 20:
            raise PDFInputError("PDF 页数不能超过 20 页")
        lines = []
        for page in pdf.pages:
            extracted = (page.extract_text() or "").strip()
            lines.append((extracted or ocr_page(page, deadline))[:30000])
            if sum(map(len, lines)) > 100000:
                raise PDFInputError("PDF 文字过多")
        text = "\n".join(lines).strip()
        photo = _extract_resume_photo(pdf.pages)
    if not text:
        raise PDFInputError("未识别出文字，请使用清晰扫描件、文字版 PDF 或手动填写。")
    document = _resume_document_from_text(text)
    document.photo = photo
    return text, document.model_dump()


def run_import(item_id):
    item = db.session.get(ResumeImport, item_id)
    if not item:
        return
    owner_lock(item.user_id)
    item = owned(ResumeImport, item.user_id, item_id, True)
    if item.state != "queued":
        db.session.commit()
        return
    content = item.content
    item.state = "running"
    db.session.commit()
    try:
        text, document = parse_pdf(content)
        error = ""
    except Exception as exc:
        text, document = "", None
        error = (
            str(exc)
            if isinstance(exc, PDFInputError)
            else "PDF 无法解析，可能已加密或损坏。请使用未加密 PDF。"
        )
    owner_lock(item.user_id)
    item = owned(ResumeImport, item.user_id, item_id, True)
    if item.state != "running":
        return
    item.content = None  # Original binary is removed after processing, including failures.
    item.state = "failed" if error else "ready"
    item.error = error
    item.text = text
    item.document = document
    db.session.commit()
