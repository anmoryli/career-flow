"""Run local UX acceptance serially; never invokes a paid model."""

import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / "output"
output.mkdir(exist_ok=True)
commands = [
    ("backend", [sys.executable, "scripts/test-integration.py"]),
    ("frontend-build", ["npm.cmd", "run", "build"]),
    ("browser", ["npx.cmd", "playwright", "test"]),
    ("exported-pdfs", [sys.executable, "scripts/verify-exported-pdfs.py"]),
]
for name, command in commands:
    print(f"Running {name}; log: output/acceptance-{name}.log", flush=True)
    with (output / f"acceptance-{name}.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        print(f"{name} failed with exit code {result.returncode}", flush=True)
        raise SystemExit(result.returncode)
    print(f"{name} passed", flush=True)
coverage = json.loads((output / "coverage.json").read_text(encoding="utf-8"))["totals"]
(output / "acceptance-summary.json").write_text(
    json.dumps(
        {
            "stages": "passed",
            "coverage": coverage,
            "real_model_verified": False,
            "production_deployed": False,
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("Local acceptance passed; real provider verification is separate.", flush=True)
