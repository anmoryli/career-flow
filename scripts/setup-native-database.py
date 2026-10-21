"""Initialize local WSL MySQL accounts without command-line passwords or container tooling."""

import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values
from pymysql.converters import escape_string
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
config = dotenv_values(root / ".env")
url = make_url(config["DATABASE_URL"])
if url.host != "127.0.0.1" or url.port != 3310 or url.database != "careerflow":
    raise SystemExit("Native setup is restricted to local port 3310 and the careerflow database")
if not re.fullmatch(r"[a-zA-Z0-9_]+", url.username or ""):
    raise SystemExit("Use an alphanumeric local database account")
password = escape_string(url.password or "")
user = url.username
sql = f"CREATE USER IF NOT EXISTS '{user}'@'localhost' IDENTIFIED BY '{password}';\n"
for name in ("careerflow", "careerflow_test", "careerflow_restore_test"):
    sql += (
        f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 "
        f"COLLATE utf8mb4_0900_ai_ci; GRANT ALL ON `{name}`.* TO '{user}'@'localhost';\n"
    )
subprocess.run(
    ["wsl", "-d", "Ubuntu", "-u", "root", "--", "mysql", "--protocol=socket"],
    input=sql.encode(),
    check=True,
)
print("Initialized local MySQL 8.4 application and isolated test databases")
