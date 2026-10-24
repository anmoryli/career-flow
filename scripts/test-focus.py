"""Run selected tests with the same environment as scripts/test-integration.py."""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
config = dotenv_values(root / ".env")
url = make_url(os.getenv("TEST_DATABASE_URL") or config["DATABASE_URL"]).set(
    database="careerflow_test"
)
env = os.environ | {key: value for key, value in config.items() if value is not None}
env.update(
    {
        "DATABASE_URL": url.render_as_string(hide_password=False),
        "TEST_DATABASE_URL": url.render_as_string(hide_password=False),
        "TEST_REDIS_URL": os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6390/15"),
        "APP_ENV": "testing",
    }
)
command = [sys.executable, "-m", "pytest", "-q", *sys.argv[1:]]
result = subprocess.run(command, cwd=root, env=env)
raise SystemExit(result.returncode)
