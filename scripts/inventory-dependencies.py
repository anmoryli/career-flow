"""Record installed runtime metadata without reading application credentials."""

import json
import re
from importlib.metadata import metadata, version
from pathlib import Path

from packaging.requirements import Requirement

root = Path(__file__).resolve().parents[1]
requirements = re.findall(
    r"^([a-zA-Z0-9_-]+==[^\n\\]+)", (root / "requirements.txt").read_text(), re.MULTILINE
)
names = []
for line in requirements:
    item = Requirement(line.strip())
    if item.marker is None or item.marker.evaluate():
        names.append(item.name)
records = []
for name in sorted(set(names)):
    info = metadata(name)
    records.append(
        {
            "name": name,
            "version": version(name),
            "license": info.get("License-Expression")
            or info.get("License")
            or "See distribution license files",
            "project_urls": info.get_all("Project-URL") or [],
        }
    )
(root / "docs/DEPENDENCIES.json").write_text(
    json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"Recorded {len(records)} runtime packages")
