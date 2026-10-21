import time

import click

from app.services.infrastructure import readiness


def register_commands(app):
    @app.cli.command("check-services")
    @click.option("--wait", default=0, type=click.IntRange(0, 180))
    def check_services(wait):
        """Check MySQL 8.4, current Alembic revision and Redis without exposing credentials."""
        deadline = time.monotonic() + wait
        while True:
            checks = readiness()
            if all(checks.values()) or time.monotonic() >= deadline:
                break
            time.sleep(2)
        for name, ok in checks.items():
            click.echo(f"{name}: {'ok' if ok else 'unavailable'}")
        if not all(checks.values()):
            raise click.ClickException("Infrastructure is not ready")
