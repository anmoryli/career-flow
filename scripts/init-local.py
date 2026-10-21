"""Create development-only secrets without overwriting existing configuration."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(".env exists; preserved unchanged")
text = (root / ".env.example").read_text(encoding="utf-8")
password = secrets.token_hex(24)
text = text.replace("replace-with-random-secret-at-least-32-characters", secrets.token_hex(32))
text = text.replace("replace-with-separate-random-secret", secrets.token_hex(32))
text = text.replace("CHANGE_ROOT_PASSWORD", secrets.token_hex(32)).replace("CHANGE_ME", password)
with target.open("x", encoding="utf-8") as file:
    file.write(text)
print("Created local .env; secrets are not displayed")
