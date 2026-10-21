import os

from dotenv import load_dotenv
from rq import SimpleWorker, Worker
from rq.timeouts import TimerDeathPenalty

from app import create_app


class WindowsDevelopmentWorker(SimpleWorker):
    # Local development only: no fork/wait4 on Windows. Linux Worker isolates production jobs.
    death_penalty_class = TimerDeathPenalty


def main():
    load_dotenv()
    app = create_app()
    with app.app_context():
        worker_class = WindowsDevelopmentWorker if os.name == "nt" else Worker
        worker_class(["careerflow"], connection=app.extensions["redis"]).work()


if __name__ == "__main__":
    main()
