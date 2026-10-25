from dotenv import load_dotenv


def infrastructure_probe() -> dict:
    """Internal queue smoke test. No user input, arbitrary code or paid model invocation."""
    from app import create_app
    from app.services.infrastructure import readiness

    load_dotenv()
    app = create_app()
    with app.app_context():
        return readiness()


def diagnosis_job(operation_id):
    from app import create_app
    from app.services.diagnosis import run_operation

    load_dotenv()
    with create_app().app_context():
        run_operation(operation_id)


def resume_ai_job(operation_id):
    from app import create_app
    from app.services.resume_ai import run_operation

    load_dotenv()
    with create_app().app_context():
        run_operation(operation_id)


def pdf_import_job(item_id):
    from app import create_app
    from app.services.pdf_import import run_import

    load_dotenv()
    with create_app().app_context():
        run_import(item_id)
