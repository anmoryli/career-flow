"""Exercise migration downgrade/upgrade and backup restore ONLY in a reserved test database."""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
config = dotenv_values(root / ".env")
url = make_url(config["DATABASE_URL"]).set(database="careerflow_restore_test")
env = os.environ | {key: value for key, value in config.items() if value is not None}
env.update(APP_ENV="testing", DATABASE_URL=url.render_as_string(hide_password=False))
engine = create_engine(url)
# Require an empty reserved database so reruns never destroy earlier test data silently.
if set(inspect(engine).get_table_names()) - {"alembic_version"}:
    raise SystemExit(
        "careerflow_restore_test must be empty; preserve/review earlier test data first"
    )


def migrate(target):
    subprocess.run(
        [sys.executable, "-m", "flask", "--app", "wsgi", "db", target],
        cwd=root,
        env=env,
        check=True,
    )


migrate("upgrade")
assert len(inspect(engine).get_table_names()) == 25
subprocess.run(
    [sys.executable, "-m", "flask", "--app", "wsgi", "db", "downgrade", "base"],
    cwd=root,
    env=env,
    check=True,
)
assert inspect(engine).get_table_names() == ["alembic_version"]
print("migration downgrade: business tables removed in isolated test DB")
migrate("upgrade")
with engine.begin() as connection:
    connection.execute(
        text(
            "INSERT INTO users(email,display_name,theme,created_at) "
            "VALUES ('restore@example.com','中文恢复 🟢','system',UTC_TIMESTAMP())"
        )
    )
dump = subprocess.run(
    [
        "wsl",
        "-d",
        "Ubuntu",
        "-u",
        "root",
        "--",
        "mysqldump",
        "--protocol=socket",
        "--single-transaction",
        "--no-tablespaces",
        "--set-gtid-purged=OFF",
        "--default-character-set=utf8mb4",
        "careerflow_restore_test",
    ],
    cwd=root,
    capture_output=True,
    check=True,
).stdout
backup = root / "output" / "restore-test.sql"
backup.write_bytes(dump)
subprocess.run(
    [sys.executable, "-m", "flask", "--app", "wsgi", "db", "downgrade", "base"],
    cwd=root,
    env=env,
    check=True,
)
subprocess.run(
    [
        "wsl",
        "-d",
        "Ubuntu",
        "-u",
        "root",
        "--",
        "mysql",
        "--protocol=socket",
        "--default-character-set=utf8mb4",
        "careerflow_restore_test",
    ],
    cwd=root,
    input=dump,
    check=True,
)
with engine.connect() as connection:
    assert connection.scalar(text("SELECT display_name FROM users")) == "中文恢复 🟢"
    assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "8d2c71ab4e90"
assert len(inspect(engine).get_table_names()) == 25
print("backup restore: 25 tables, revision and Chinese/emoji row verified")
subprocess.run(
    [sys.executable, "-m", "flask", "--app", "wsgi", "db", "downgrade", "base"],
    cwd=root,
    env=env,
    check=True,
)
print("Reserved native restore database returned to base for repeatable checks")
engine.dispose()
