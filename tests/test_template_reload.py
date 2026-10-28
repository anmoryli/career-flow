import os

from app import create_app
from app.config import load_config


def test_development_reloads_changed_template(config, tmp_path):
    config["APP_ENV"] = "development"
    app = create_app(config)
    app.jinja_loader.searchpath = [str(tmp_path)]
    template = tmp_path / "reload.html"
    template.write_text("before", encoding="utf-8")
    assert app.jinja_env.get_template("reload.html").render() == "before"
    template.write_text("after", encoding="utf-8")
    # Ensure a changed timestamp even on filesystems with coarse time resolution.
    modified = template.stat().st_mtime + 2
    os.utime(template, (modified, modified))
    assert app.jinja_env.get_template("reload.html").render() == "after"


def test_template_reload_defaults_off_outside_development(config):
    config["APP_ENV"] = "testing"
    assert load_config(config)["TEMPLATES_AUTO_RELOAD"] is False


def test_explicit_template_reload_setting_is_preserved(config):
    config.update(APP_ENV="development", TEMPLATES_AUTO_RELOAD=False)
    assert load_config(config)["TEMPLATES_AUTO_RELOAD"] is False
