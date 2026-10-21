import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from rq import Queue

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

load_dotenv()
from app import create_app  # noqa: E402
from app.jobs import infrastructure_probe  # noqa: E402

app = create_app()
queue = Queue("careerflow", connection=app.extensions["redis"])
job = queue.enqueue(infrastructure_probe, job_timeout=30, result_ttl=120, failure_ttl=120)
for _ in range(40):
    status = job.get_status(refresh=True)
    if status == "finished":
        assert job.return_value() == {"mysql": True, "schema": True, "redis": True}
        print("Native RQ worker: job finished, MySQL/schema/Redis all healthy")
        job.delete()
        break
    if status == "failed":
        raise SystemExit("Native RQ probe failed; inspect worker logs")
    time.sleep(1)
else:
    raise SystemExit("Native RQ probe timed out")
