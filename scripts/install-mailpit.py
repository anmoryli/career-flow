"""Install the pinned native Windows Mailpit binary from the official HTTPS release."""

import hashlib
import io
import json
import subprocess
import urllib.request
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cache = root / "output" / "native-downloads"
cache.mkdir(parents=True, exist_ok=True)
url = "https://github.com/axllent/mailpit/releases/download/v1.27.10/mailpit-windows-amd64.zip"
archive = cache / "mailpit-windows-amd64.zip"
if not archive.exists():
    urllib.request.urlretrieve(url, archive)
data = archive.read_bytes()
with zipfile.ZipFile(io.BytesIO(data)) as z:
    assert z.testzip() is None
    member = next(n for n in z.namelist() if n == "mailpit.exe")
    executable = root / "instance" / "tools" / "mailpit.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(z.read(member))
record = {
    "source": url,
    "sha256": hashlib.sha256(data).hexdigest(),
    "integrity": "ZIP CRC checked; upstream release provides no checksum asset",
}
(cache / "mailpit-download.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
subprocess.run([str(executable), "--help"], check=True, capture_output=True)
print("Installed native Mailpit; source and SHA256 recorded locally")
