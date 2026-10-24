import os

from dotenv import load_dotenv
from rq import SimpleWorker, Worker
from rq.timeouts import TimerDeathPenalty

from app import create_app


class TaskRecoveryMixin:
    def run_maintenance_tasks(self):
        super().run_maintenance_tasks()
        from flask import current_app
        from sqlalchemy.exc import SQLAlchemyError

        from app.extensions import db
        from app.services.diagnosis import recover_stale_tasks

        try:
            recover_stale_tasks()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.error("task_recovery_database_unavailable")


class CareerFlowWorker(TaskRecoveryMixin, Worker):
    pass


class WindowsDevelopmentWorker(TaskRecoveryMixin, SimpleWorker):
    # Local development only: no fork/wait4 on Windows. Linux Worker isolates production jobs.
    death_penalty_class = TimerDeathPenalty


def main():
    load_dotenv()
    app = create_app()
    with app.app_context():
        worker_class = WindowsDevelopmentWorker if os.name == "nt" else CareerFlowWorker
        worker_class(
            ["careerflow"], connection=app.extensions["redis"], maintenance_interval=60
        ).work()


if __name__ == "__main__":
    main()
