"""Capture literal commands, exit codes and outputs without including configuration secrets."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / "output"
output.mkdir(exist_ok=True)
record = {"at": datetime.now(UTC).isoformat(), "runtime": "native Windows + WSL Ubuntu", "runs": []}
commands = [
    ["git", "ls-tree", "--name-only", "db70a3d"],
    ["uv", "run", "ruff", "check", "app", "tests", "scripts", "wsgi.py"],
    ["uv", "run", "ruff", "format", "--check", "app", "tests", "scripts", "wsgi.py", "migrations"],
    [sys.executable, str(root / "scripts" / "test-integration.py")],
    [sys.executable, str(root / "scripts" / "verify-db-lifecycle.py")],
    [sys.executable, str(root / "scripts" / "verify-worker.py")],
    [sys.executable, "-m", "flask", "--app", "wsgi", "check-services"],
    ["node", "scripts/build-assets.cjs"],
]
for command in commands:
    result = subprocess.run(
        command, cwd=root, capture_output=True, encoding="utf-8", errors="replace"
    )
    item = {
        "command": command,
        "exit_status": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    record["runs"].append(item)
    print(f"{command[0]} {command[-1]}: exit={result.returncode}")
record["originals"] = {}
for name in ("AGENT.md", "AI_AGENT_POLICY.md", "PROMPT.md"):
    original = subprocess.run(
        ["git", "show", f"db70a3d:{name}"], cwd=root, capture_output=True, check=True
    ).stdout
    current = (root / name).read_bytes()
    current_blob = subprocess.run(
        ["git", "hash-object", name], cwd=root, capture_output=True, check=True
    ).stdout.strip()
    baseline_blob = subprocess.run(
        ["git", "rev-parse", f"db70a3d:{name}"], cwd=root, capture_output=True, check=True
    ).stdout.strip()
    record["originals"][name] = {
        "sha256": hashlib.sha256(current).hexdigest(),
        "baseline_blob": baseline_blob.decode(),
        "matches_baseline": current_blob == baseline_blob,
        "comparison": "Git clean-filter blob comparison (repository newline policy)",
    }
(output / "verification-native.json").write_text(
    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
)
if any(item["exit_status"] for item in record["runs"]):
    raise SystemExit(1)
if not all(item["matches_baseline"] for item in record["originals"].values()):
    raise SystemExit("Original input documents changed")
print("Verified commands and preserved baseline hashes recorded")
