from dotenv import load_dotenv


def infrastructure_probe() -> dict:
    """Internal queue smoke test. No user input, arbitrary code or paid model invocation."""
    from app import create_app
    from app.services.infrastructure import readiness

    load_dotenv()
    app = create_app()
    with app.app_context():
        return readiness()
