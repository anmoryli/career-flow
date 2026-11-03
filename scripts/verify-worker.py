import sys
import time
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

load_dotenv()
from app import create_app  # noqa: E402
from app.services import task_queue  # noqa: E402

app = create_app()
with app.app_context():
    task_id = uuid4().hex
    task_queue.enqueue("probe", task_id, 30)
    for _ in range(60):
        payload = task_queue.result("probe", task_id)
        if payload == {"mysql": True, "schema": True, "redis": True}:
            print("Native task worker: probe finished, MySQL/schema/Redis all healthy")
            break
        time.sleep(1)
    else:
        raise SystemExit("Native worker probe timed out; inspect worker logs")
