"""Run tests against an isolated native MySQL database."""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
config = dotenv_values(root / ".env")
url = make_url(os.getenv("TEST_DATABASE_URL") or config["DATABASE_URL"]).set(
    database="careerflow_test"
)
if url.host not in {"localhost", "127.0.0.1"}:
    raise SystemExit("Default integration runner accepts local databases only")
engine = create_engine(url)
with engine.connect() as connection:
    if not connection.scalar(text("SELECT VERSION()")).startswith("8.4."):
        raise SystemExit("MySQL 8.4 is required")
engine.dispose()
env = os.environ | {key: value for key, value in config.items() if value is not None}
env.update(
    {
        "DATABASE_URL": url.render_as_string(hide_password=False),
        "TEST_DATABASE_URL": url.render_as_string(hide_password=False),
        "TEST_REDIS_URL": os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6390/15"),
        "APP_ENV": "testing",
    }
)
(root / "output").mkdir(exist_ok=True)
for command in [
    [sys.executable, "-m", "flask", "--app", "wsgi", "db", "upgrade"],
    [sys.executable, "-m", "flask", "--app", "wsgi", "db", "check"],
    [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--junitxml=output/pytest-native.xml",
        "--cov=app",
        "--cov-branch",
        "--cov-report=term-missing",
        "--cov-report=html:output/coverage",
        "--cov-report=json:output/coverage.json",
    ],
]:
    result = subprocess.run(command, cwd=root, env=env)
    if result.returncode:
        raise SystemExit(result.returncode)
