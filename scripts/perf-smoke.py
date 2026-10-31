"""HTTP load smoke test for CareerFlow.

Deliberately dependency-free (standard library only) so it can run in CI and on a
fresh checkout without installing anything beyond the app requirements.

Usage:
    uv run python scripts/perf-smoke.py --base-url http://127.0.0.1:8020 --duration 10

Thresholds come from environment variables with conservative defaults; the script
exits non-zero when a budget is exceeded so CI fails loudly instead of reporting a
green build that nobody looked at.
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

STATIC_P95_MS = float(os.getenv("PERF_P95_STATIC_MS", "150"))
HTML_P95_MS = float(os.getenv("PERF_P95_HTML_MS", "500"))
READY_P95_MS = float(os.getenv("PERF_P95_READY_MS", "800"))
MAX_ERROR_RATE = float(os.getenv("PERF_MAX_ERROR_RATE", "0.01"))
MIN_RPS = float(os.getenv("PERF_MIN_RPS", "10"))


@dataclass
class Endpoint:
    path: str
    kind: str
    budget_ms: float


@dataclass
class Result:
    endpoint: Endpoint
    latencies: list[float] = field(default_factory=list)
    statuses: dict[int, int] = field(default_factory=dict)
    errors: int = 0
    started: float = 0.0
    finished: float = 0.0

    @property
    def total(self) -> int:
        return len(self.latencies) + self.errors

    @property
    def error_count(self) -> int:
        return self.errors + sum(n for code, n in self.statuses.items() if code >= 400)

    @property
    def error_rate(self) -> float:
        return self.error_count / self.total if self.total else 1.0

    @property
    def rps(self) -> float:
        elapsed = max(self.finished - self.started, 0.001)
        return self.total / elapsed

    def percentile(self, value: float) -> float:
        if not self.latencies:
            return 0.0
        ordered = sorted(self.latencies)
        index = min(round(value / 100 * (len(ordered) - 1)), len(ordered) - 1)
        return ordered[index]

    def summary(self) -> dict:
        return {
            "path": self.endpoint.path,
            "kind": self.endpoint.kind,
            "budget_ms": self.endpoint.budget_ms,
            "requests": self.total,
            "rps": round(self.rps, 1),
            "errors": self.error_count,
            "error_rate": round(self.error_rate, 4),
            "p50_ms": round(self.percentile(50), 1),
            "p95_ms": round(self.percentile(95), 1),
            "p99_ms": round(self.percentile(99), 1),
            "max_ms": round(max(self.latencies), 1) if self.latencies else 0.0,
            "statuses": {str(k): v for k, v in sorted(self.statuses.items())},
        }


def one_request(url: str, timeout: float = 10.0) -> tuple[int | None, float]:
    request = urllib.request.Request(url, headers={"User-Agent": "careerflow-perf-smoke"})
    # 压测目标是本机/内网服务；显式绕过 HTTP(S)_PROXY，避免把请求发给代理后测出假延迟。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=timeout) as response:
            response.read()
            return response.status, (time.perf_counter() - started) * 1000
    except urllib.error.HTTPError as error:
        error.read()
        return error.code, (time.perf_counter() - started) * 1000
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, (time.perf_counter() - started) * 1000


def worker(
    endpoint: Endpoint, base_url: str, deadline: float, result: Result, lock: threading.Lock
):
    url = base_url.rstrip("/") + endpoint.path
    while time.monotonic() < deadline:
        status, latency = one_request(url)
        with lock:
            result.latencies.append(latency)
            if status is None:
                result.errors += 1
            else:
                result.statuses[status] = result.statuses.get(status, 0) + 1


def run(endpoint: Endpoint, base_url: str, duration: float, concurrency: int) -> Result:
    # Warm up once so template compilation and connection setup do not dominate p95.
    one_request(base_url.rstrip("/") + endpoint.path)
    result = Result(endpoint=endpoint)
    lock = threading.Lock()
    result.started = time.monotonic()
    deadline = result.started + duration
    threads = [
        threading.Thread(
            target=worker, args=(endpoint, base_url, deadline, result, lock), daemon=True
        )
        for _ in range(concurrency)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    result.finished = time.monotonic()
    return result


def markdown(rows: list[dict], passed: bool) -> str:
    header = (
        "| 端点 | 类型 | 请求数 | RPS | p50 | p95 | p99 | 错误率 | 预算 p95 | 结果 |\n"
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |\n"
    )
    body = "".join(
        f"| `{row['path']}` | {row['kind']} | {row['requests']} | {row['rps']} | "
        f"{row['p50_ms']}ms | {row['p95_ms']}ms | {row['p99_ms']}ms | "
        f"{row['error_rate'] * 100:.2f}% | {row['budget_ms']}ms | "
        f"{'PASS' if row['passed'] else 'FAIL'} |\n"
        for row in rows
    )
    return header + body + ("\n整体结果：**通过**\n" if passed else "\n整体结果：**未通过**\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="CareerFlow HTTP load smoke test")
    parser.add_argument("--base-url", default=os.getenv("PERF_BASE_URL", "http://127.0.0.1:8020"))
    parser.add_argument("--duration", type=float, default=float(os.getenv("PERF_DURATION", "8")))
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("PERF_CONCURRENCY", "8")))
    parser.add_argument("--json-out", default="output/perf/report.json")
    parser.add_argument(
        "--endpoints",
        default=os.getenv(
            "PERF_ENDPOINTS",
            "/health/live:health,/health/ready:ready,/:html,/login:html,"
            "/guides:html,/guides/backend-engineer:html,/robots.txt:static,"
            "/static/css/frontend/utilities.css:static",
        ),
        help="逗号分隔的 path:kind 列表，kind 取 health/ready/html/static",
    )
    args = parser.parse_args()

    budgets = {"health": 200.0, "ready": READY_P95_MS, "html": HTML_P95_MS, "static": STATIC_P95_MS}
    endpoints = []
    for item in args.endpoints.split(","):
        item = item.strip()
        if not item:
            continue
        path, _, kind = item.partition(":")
        kind = kind or "html"
        endpoints.append(Endpoint(path=path, kind=kind, budget_ms=budgets.get(kind, HTML_P95_MS)))

    rows = []
    raw = []
    for endpoint in endpoints:
        result = run(endpoint, args.base_url, args.duration, args.concurrency)
        summary = result.summary()
        passed = (
            summary["p95_ms"] <= endpoint.budget_ms
            and summary["error_rate"] <= MAX_ERROR_RATE
            and summary["rps"] >= MIN_RPS
        )
        summary["passed"] = passed
        rows.append(summary)
        raw.append(summary)
        print(
            f"{endpoint.path:<42} {summary['requests']:>5} req  "
            f"{summary['rps']:>6.1f} rps  p95 {summary['p95_ms']:>7.1f}ms  "
            f"err {summary['error_rate'] * 100:>5.2f}%  {'PASS' if passed else 'FAIL'}"
        )

    overall = all(row["passed"] for row in rows)
    report = {
        "base_url": args.base_url,
        "duration_s": args.duration,
        "concurrency": args.concurrency,
        "thresholds": {
            "html_p95_ms": HTML_P95_MS,
            "static_p95_ms": STATIC_P95_MS,
            "ready_p95_ms": READY_P95_MS,
            "max_error_rate": MAX_ERROR_RATE,
            "min_rps": MIN_RPS,
        },
        "passed": overall,
        "endpoints": raw,
    }
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入 {out}")

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(markdown(raw, overall), encoding="utf-8")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
