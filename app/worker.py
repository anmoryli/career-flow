"""Background task worker: Redis Streams consumer, no RQ.

Each task runs in a spawned subprocess with the same hard timeout the queue
used to enforce; a task whose worker dies mid-run is re-claimed from the
stream's pending list on the next maintenance pass, and the state checks in
every job body make that redelivery safe. The process entry point
(`python -m app.worker`) and the maintenance contract are unchanged.
"""

import time
from multiprocessing import get_context

from dotenv import load_dotenv

MAINTENANCE_INTERVAL = 60
JOB_GRACE_SECONDS = 30
# Spawn on every platform: job bodies build their own Flask app, and a
# spawned child re-imports this module without running main().
PROCESS_CONTEXT = get_context("spawn")


def create_app():
    from app import create_app as factory

    return factory()


def job_entry(kind, task_id):
    """Subprocess body: build a fresh app context and run the job."""
    load_dotenv()
    app = create_app()
    if kind == "probe":
        from app.jobs import infrastructure_probe

        with app.app_context():
            payload = infrastructure_probe()
        import redis as redis_lib

        from app.services import task_queue

        client = redis_lib.from_url(task_queue.redis_url())
        task_queue.report("probe", task_id, payload, redis_client=client)
        return
    from app.jobs import diagnosis_job, pdf_import_job, resume_ai_job

    jobs = {
        "diagnosis": diagnosis_job,
        "resume-ai": resume_ai_job,
        "pdf-import": pdf_import_job,
    }
    job = jobs.get(kind)
    if job is None:
        raise SystemExit(f"unknown task kind: {kind}")
    with app.app_context():
        job(int(task_id))


def run_task(fields, redis_client=None):
    """Run one claimed task to completion (or hard timeout) in a subprocess."""
    kind = fields["kind"]
    task_id = fields["id"]
    timeout = int(fields.get("timeout") or 120) + JOB_GRACE_SECONDS
    process = PROCESS_CONTEXT.Process(
        target=job_entry, args=(kind, task_id), daemon=True
    )
    process.start()
    process.join(timeout)
    if process.is_alive():
        from flask import current_app

        current_app.logger.error(
            "task_timeout operation=%s kind=%s timeout_seconds=%s", task_id, kind, timeout
        )
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
    if process.exitcode not in (0, None):
        from flask import current_app

        current_app.logger.warning(
            "task_exit_nonzero operation=%s kind=%s exitcode=%s",
            task_id,
            kind,
            process.exitcode,
        )


def run_maintenance():
    """Recover stale rows and re-claim tasks orphaned by a dead worker."""
    from flask import current_app
    from sqlalchemy.exc import SQLAlchemyError

    from app.extensions import db
    from app.services import task_queue
    from app.services.diagnosis import recover_stale_tasks

    try:
        for message_id, fields in task_queue.reclaim_stale():
            try:
                run_task(fields)
            finally:
                task_queue.ack(message_id)
        recover_stale_tasks()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("task_recovery_database_unavailable")
    except Exception as error:
        db.session.rollback()
        current_app.logger.error("task_reclaim_failed type=%s", type(error).__name__)


def serve(redis_client, once=False, block_ms=5000, consumer="worker"):
    """Consume the task stream until stopped (or one pass when once=True)."""
    from app.services import task_queue

    task_queue.ensure_group(redis_client)
    next_maintenance = 0.0
    while True:
        if time.monotonic() >= next_maintenance:
            run_maintenance()
            next_maintenance = time.monotonic() + MAINTENANCE_INTERVAL
        for message_id, fields in task_queue.claim(
            block_ms=block_ms, consumer=consumer, redis_client=redis_client
        ):
            try:
                run_task(fields, redis_client=redis_client)
            except Exception:
                from flask import current_app

                current_app.logger.exception("task_run_failed operation=%s", fields.get("id"))
            finally:
                task_queue.ack(message_id, redis_client=redis_client)
        if once:
            return


def main():
    load_dotenv()
    app = create_app()
    with app.app_context():
        serve(app.extensions["redis"])


if __name__ == "__main__":
    main()
