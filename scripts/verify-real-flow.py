"""Drive the real HTTP surface end to end against the real providers.

Registers a throwaway account through the real mail path (Mailpit), buys the
membership through the mock payment switch, then walks every model-backed
product path: paste-to-resume, paragraph rewrite, job analysis, follow-up,
report, suggestions, export, import and guest parsing.

    python scripts/verify-real-flow.py --out output/real-model/flow.json

Requires the real Flask server and an RQ worker on the local development
database; nothing here stubs the provider.
"""

import argparse
import json
import re
import time
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
MAILPIT = "http://127.0.0.1:8026"
TERMINAL = {"succeeded", "failed", "cancelled"}

SOURCE_TEXT = (
    "我叫林望舒，做 B 端产品 6 年。2021 年 4 月到现在在杭州云链科技做高级产品经理，"
    "负责供应商协同平台的订单与对账模块，覆盖 320 家供应商，把月度对账周期从 7 天压缩到 2 天。"
    "2018 年 7 月到 2021 年 3 月在宁波智造软件做产品经理，负责仓储管理系统的入库和盘点流程，"
    "支持 4 个仓库上线。本科读的是浙江工业大学信息管理与信息系统，2014 到 2018 年。"
)

JD = """岗位：供应链产品经理（B 端）
职责：
1. 负责供应商协同与对账产品的规划与迭代；
2. 梳理业务流程，输出需求文档与原型；
3. 与研发、运营协作推动上线，并用数据验证效果。
要求：
1. 3 年以上 B 端产品经验，熟悉供应链或财务对账场景；
2. 具备数据分析能力，能独立完成指标拆解；
3. 有跨部门项目推动经验，沟通表达清晰。
加分项：了解 SQL，做过 SaaS 商业化。"""


def simple_pdf(lines):
    """A minimal single-page PDF with ASCII text, enough for the import parser."""
    text = "BT /F1 12 Tf 60 760 Td 16 TL " + " ".join(
        f"({line}) Tj T*" for line in lines
    ) + " ET"
    stream = text.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


class Flow:
    def __init__(self):
        self.client = httpx.Client(base_url=BASE, timeout=60, follow_redirects=False)
        self.mail = httpx.Client(base_url=MAILPIT, timeout=20)
        self.steps = []
        self.started = time.monotonic()

    def token(self, path="/workspace"):
        page = self.client.get(path)
        found = re.search(r'name="csrf-token" content="([^"]+)"', page.text)
        if not found:
            raise RuntimeError(f"{path} 未返回 csrf token（HTTP {page.status_code}）")
        return found.group(1)

    def api(self, method, path, payload=None, timeout=60):
        headers = {"X-CSRFToken": self.token()}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        return self.client.request(method, path, json=payload, headers=headers, timeout=timeout)

    def step(self, name, ok, detail="", elapsed=None):
        record = {
            "name": name,
            "ok": bool(ok),
            "detail": detail,
            "elapsed": round(elapsed if elapsed is not None else 0, 2),
        }
        self.steps.append(record)
        print(f"  {'OK  ' if ok else 'FAIL'} {name:<34} {record['elapsed']:6.2f}s {detail}")
        return record

    def run(self, name, fn, timeout=240):
        started = time.monotonic()
        try:
            detail = fn()
            return self.step(name, True, detail or "", time.monotonic() - started)
        except Exception as error:  # noqa: BLE001 - verification harness
            detail = f"{type(error).__name__}: {str(error)[:160]}"
            self.step(name, False, detail, time.monotonic() - started)
            return None

    def wait(self, path, timeout=240):
        deadline = time.monotonic() + timeout
        last = {}
        while time.monotonic() < deadline:
            response = self.client.get(path)
            last = response.json()
            if last.get("state") in TERMINAL:
                return last
            time.sleep(1.5)
        raise RuntimeError(f"等待超时 state={last.get('state')} error={last.get('error')}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output/real-model/flow.json")
    args = parser.parse_args()
    flow = Flow()
    email = f"real-flow-{uuid.uuid4().hex[:10]}@example.com"
    password = "Real-model-flow-2026"
    state = {}

    def public_surface():
        home = flow.client.get("/")
        assert home.status_code == 200, home.status_code
        workspace = flow.client.get("/workspace")
        assert workspace.status_code in {302, 303, 401}, workspace.status_code
        live = flow.client.get("/health/live")
        assert live.status_code == 200
        return f"home={home.status_code} anonymous workspace={workspace.status_code}"

    def register():
        token = flow.token("/register")
        sent = flow.client.post(
            "/auth/code", data={"csrf_token": token, "email": email}
        )
        assert sent.status_code in {200, 303}, sent.status_code
        code = ""
        for _ in range(20):
            messages = flow.mail.get("/api/v1/messages").json().get("messages", [])
            match = next(
                (item for item in messages if email in json.dumps(item.get("To", []))), None
            )
            if match:
                detail = flow.mail.get(f"/api/v1/message/{match['ID']}").json()
                found = re.findall(r"\d{6}", detail.get("Text") or "")
                if found:
                    code = found[0]
                    break
            time.sleep(1)
        assert code, "Mailpit 中没有收到验证码邮件"
        token = flow.token("/register")
        created = flow.client.post(
            "/register",
            data={
                "csrf_token": token,
                "display_name": "真实链路测试",
                "email": email,
                "password": password,
                "code": code,
            },
        )
        assert created.status_code == 303, created.status_code
        assert flow.client.cookies.get("cf_session"), "注册后没有会话 cookie"
        return f"email={email} code={code} → 303"

    def landing_signed_in():
        home = flow.client.get("/")
        assert home.status_code == 200, home.status_code
        has_landing = "cf-landing" in home.text or "cf-hero" in home.text
        workspace = flow.client.get("/workspace")
        assert workspace.status_code == 200, workspace.status_code
        return f"home=200 landing={has_landing} workspace=200"

    def membership():
        response = flow.api(
            "POST", "/commerce/orders", {"request_key": str(uuid.uuid4()), "plan_code": "membership_quarterly"}
        )
        assert response.status_code in {302, 303}, response.status_code
        page = flow.client.get("/workspace?view=billing")
        assert page.status_code == 200
        return "membership_90 下单并即时结算"

    def create_resume():
        response = flow.api(
            "POST",
            "/api/resumes",
            {
                "request_key": str(uuid.uuid4()),
                "revision": 0,
                "title": "真实链路简历",
                "document": {"name": "林望舒", "role": "产品经理"},
            },
        )
        assert response.status_code == 201, f"{response.status_code} {response.text[:120]}"
        item = response.json()
        state["resume_id"] = item["id"]
        state["revision"] = item["revision"]
        return f"resume_id={item['id']} revision={item['revision']}"

    def compose():
        response = flow.api(
            "POST",
            f"/api/resumes/{state['resume_id']}/ai/compose/start",
            {
                "request_key": str(uuid.uuid4()),
                "revision": state["revision"],
                "source": SOURCE_TEXT,
            },
        )
        assert response.status_code == 200, f"{response.status_code} {response.text[:160]}"
        operation = response.json()
        result = flow.wait(f"/api/resume-ai/{operation['id']}")
        assert result["state"] == "succeeded", result.get("error")
        document = result["result"]["document"]
        state["compose"] = document
        numbers = set(re.findall(r"\d+(?:[.,]\d+)?%?", json.dumps(document, ensure_ascii=False)))
        assert numbers <= set(re.findall(r"\d+(?:[.,]\d+)?%?", SOURCE_TEXT)), numbers
        assert document["experiences"], "草稿没有工作经历"
        adopted = flow.api(
            "POST",
            f"/api/resumes/{state['resume_id']}/adoptions",
            {"request_key": str(uuid.uuid4()), "operation_id": operation["id"]},
        )
        assert adopted.status_code == 200, adopted.status_code
        return (
            f"op={operation['id']} 经历={len(document['experiences'])} "
            f"技能组={len(document['skills'])} 字段数={len(document)}"
        )

    def save_draft():
        document = dict(state["compose"])
        response = flow.api(
            "POST",
            f"/api/resumes/{state['resume_id']}",
            {
                "request_key": str(uuid.uuid4()),
                "revision": state["revision"],
                "title": "真实链路简历",
                "document": document,
            },
        )
        assert response.status_code == 200, f"{response.status_code} {response.text[:160]}"
        state["revision"] = response.json()["revision"]
        return f"保存后 revision={state['revision']}"

    def rewrite():
        response = flow.api(
            "POST",
            f"/api/resumes/{state['resume_id']}/ai/start",
            {
                "request_key": str(uuid.uuid4()),
                "revision": state["revision"],
                "mode": "optimize",
                "path": "experiences.0.bullets.0",
                "requirement": "突出业务结果，保持事实不变",
            },
        )
        assert response.status_code == 200, f"{response.status_code} {response.text[:160]}"
        operation = response.json()
        result = flow.wait(f"/api/resume-ai/{operation['id']}")
        assert result["state"] == "succeeded", result.get("error")
        proposed = result["result"]["proposed"]
        assert proposed.strip(), "改写结果为空"
        state["rewrite"] = result["result"]
        return f"op={operation['id']} 改写 {len(proposed)} 字：{proposed[:40]}…"

    def create_job():
        response = flow.api(
            "POST",
            "/api/jobs",
            {
                "request_key": str(uuid.uuid4()),
                "resume_id": state["resume_id"],
                "resume_revision": state["revision"],
                "title": "供应链产品经理",
                "company": "示例供应链科技",
                "description": JD,
            },
        )
        assert response.status_code == 201, f"{response.status_code} {response.text[:160]}"
        job = response.json()
        state["job_id"] = job["id"]
        return f"job_id={job['id']}"

    def open_job():
        page = flow.client.get(f"/jobs/{state['job_id']}")
        assert page.status_code == 200, page.status_code
        diagnostic = re.search(r'data-diagnostic="(\d+)"', page.text)
        revision = re.search(r'data-revision="(\d+)"', page.text)
        assert diagnostic and revision, "诊断页缺少 data-diagnostic / data-revision"
        state["diagnostic_id"] = int(diagnostic.group(1))
        state["diagnostic_revision"] = int(revision.group(1))
        return f"diagnostic_id={state['diagnostic_id']} revision={state['diagnostic_revision']}"

    def analysis():
        response = flow.api(
            "POST",
            f"/api/diagnostics/{state['diagnostic_id']}/start",
            {"request_key": str(uuid.uuid4()), "kind": "analysis"},
        )
        assert response.status_code == 200, f"{response.status_code} {response.text[:160]}"
        operation = response.json()
        result = flow.wait(f"/api/operations/{operation['id']}")
        assert result["state"] == "succeeded", result.get("error")
        state["analysis"] = result["result"]
        state["analysis_op"] = operation["id"]
        dimensions = result["result"]["dimensions"]
        assert len(dimensions) == 5, dimensions
        scores = ", ".join(f"{d['name']}:{d['score']}" for d in dimensions)
        return (
            f"op={operation['id']} 维度={{{scores}}} "
            f"问题数={len(result['result']['findings'])} 建议={len(result['result']['suggestions'])}"
        )

    def follow_up():
        page = flow.client.get(f"/jobs/{state['job_id']}")
        found = re.search(r'data-revision="(\d+)"', page.text)
        assert found, "诊断页没有 revision"
        revision = int(found.group(1))
        question = (state.get("analysis") or {}).get("question") or ""
        if not question:
            return "本轮模型未追问，跳过回答"
        response = flow.api(
            "POST",
            f"/api/diagnostics/{state['diagnostic_id']}/answer",
            {
                "request_key": str(uuid.uuid4()),
                "revision": revision,
                "answer": "我负责差异场景的归类规则和复核队列设计，与财务共同确定 12 类差异的处理优先级。",
            },
        )
        assert response.status_code == 200, f"{response.status_code} {response.text[:160]}"
        return f"已回答（revision={revision}）：{question[:36]}…"

    def report():
        response = flow.api(
            "POST",
            f"/api/diagnostics/{state['diagnostic_id']}/start",
            {"request_key": str(uuid.uuid4()), "kind": "report"},
        )
        assert response.status_code == 200, f"{response.status_code} {response.text[:160]}"
        operation = response.json()
        result = flow.wait(f"/api/operations/{operation['id']}")
        assert result["state"] == "succeeded", result.get("error")
        state["report_op"] = operation["id"]
        page = flow.client.get(f"/jobs/{state['job_id']}/report")
        assert page.status_code == 200, page.status_code
        suggestions = flow.client.get(
            f"/jobs/{state['job_id']}/suggestions?operation_id={operation['id']}"
        )
        assert suggestions.status_code == 200, suggestions.status_code
        return (
            f"op={operation['id']} 建议={len(result['result']['suggestions'])} "
            f"报告页=200 逐段页=200"
        )

    def apply_suggestion():
        response = flow.api(
            "POST",
            f"/api/operations/{state['report_op']}/apply",
            {
                "request_key": str(uuid.uuid4()),
                "indices": [0],
                "confirmed": "yes",
                "title": "真实链路 · 岗位版本",
            },
        )
        assert response.status_code == 201, f"{response.status_code} {response.text[:160]}"
        resume = response.json()
        state["applied_resume_id"] = resume["id"]
        return f"另存岗位版本 resume_id={resume['id']}"

    def export():
        response = flow.api(
            "POST",
            f"/api/resumes/{state['resume_id']}/export",
            {"request_key": str(uuid.uuid4()), "revision": state["revision"]},
        )
        assert response.status_code == 200, f"{response.status_code} {response.text[:160]}"
        url = response.json()["url"]
        page = flow.client.get(url)
        assert page.status_code == 200, page.status_code
        assert "林望舒" in page.text, "打印页缺少姓名"
        return f"打印页 {url} 含姓名"

    def upload_pdf():
        pdf = simple_pdf(
            [
                "Alex Chen",
                "Product Manager",
                "Summary: six years of B2B product work on supplier reconciliation.",
                "Experience: Hangzhou Cloudlink, senior product manager, 2021 to now.",
                "Education: Zhejiang University of Technology, 2014 to 2018.",
            ]
        )
        headers = {"X-CSRFToken": flow.token()}
        response = flow.client.post(
            "/api/imports",
            files={"file": ("candidate.pdf", pdf, "application/pdf")},
            data={"request_key": str(uuid.uuid4())},
            headers=headers,
        )
        assert response.status_code in {200, 201}, f"{response.status_code} {response.text[:160]}"
        item = response.json()
        deadline = time.monotonic() + 90
        status = {}
        while time.monotonic() < deadline:
            status = flow.client.get(f"/api/imports/{item['id']}").json()
            if status.get("state") in {"ready", "failed"}:
                break
            time.sleep(1)
        assert status.get("state") == "ready", status
        return f"import_id={item['id']} state={status['state']}"

    def guest_parse():
        client = httpx.Client(base_url=BASE, timeout=60, follow_redirects=False)
        page = client.get("/")
        token = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)
        pdf = simple_pdf(
            ["Guest Candidate", "Product Manager", "Summary: guest upload path check."]
        )
        response = client.post(
            "/api/guest/resume/parse",
            files={"file": ("guest.pdf", pdf, "application/pdf")},
            headers={"X-CSRFToken": token},
        )
        assert response.status_code == 200, f"{response.status_code} {response.text[:160]}"
        payload = response.json()
        return f"游客解析字段={sorted(payload)[:5]}"

    def theme():
        response = flow.api("POST", "/settings/theme", {"theme": "dark"})
        assert response.status_code == 200, response.status_code
        page = flow.client.get("/workspace")
        assert page.status_code == 200
        return "深色主题已保存"

    flow.run("匿名公开面", public_surface)
    flow.run("注册（真实邮件）", register)
    flow.run("登录后首页仍是 landing", landing_signed_in)
    flow.run("开通会员", membership)
    flow.run("新建简历", create_resume)
    flow.run("粘贴文字 → AI 整理", compose)
    flow.run("保存草稿", save_draft)
    flow.run("AI 段落改写", rewrite)
    flow.run("新建岗位", create_job)
    flow.run("打开诊断页", open_job)
    flow.run("岗位分析（真实模型）", analysis)
    flow.run("诊断追问", follow_up)
    flow.run("最终报告", report)
    flow.run("应用建议另存岗位版本", apply_suggestion)
    flow.run("导出打印页", export)
    flow.run("PDF 导入解析", upload_pdf)
    flow.run("游客 PDF 解析", guest_parse)
    flow.run("主题设置", theme)

    payload = {
        "email": email,
        "started": round(time.monotonic() - flow.started, 1),
        "steps": flow.steps,
        "artifacts": {
            "analysis": state.get("analysis"),
            "report_operation": state.get("report_op"),
            "rewrite": state.get("rewrite"),
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [item for item in flow.steps if not item["ok"]]
    print(f"\n{len(flow.steps) - len(failed)}/{len(flow.steps)} 步通过，耗时 {payload['started']}s → {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
