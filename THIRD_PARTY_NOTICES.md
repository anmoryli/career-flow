# Third-party notices · CareerFlow V1

No third-party resume/application repository was copied into this project. The implementation uses upstream libraries; upstream default UI templates, external fonts, images and model weights are not bundled.

## Direct runtime dependencies

| Library | Purpose | Upstream license |
|---|---|---|
| Flask / Werkzeug / Jinja2 / Flask-SQLAlchemy | HTTP, templates, passwords, ORM integration | BSD-3-Clause |
| SQLAlchemy / Alembic / Flask-Migrate | ORM and schema migration | MIT |
| PyMySQL | MySQL driver | MIT |
| Flask-WTF / WTForms | CSRF protection | BSD-3-Clause |
| Pydantic / email-validator | Strict input validation | MIT / Unlicense |
| redis-py / RQ | Redis client and job queue | MIT / BSD-2-Clause |
| python-dotenv | Local environment configuration | BSD-3-Clause |
| Gunicorn | Linux production WSGI server | MIT |

Exact installed versions, upstream metadata and transitive runtime license declarations are recorded in `docs/DEPENDENCIES.json`; hashes and exact resolved artifacts are in `uv.lock` and `requirements.txt`. SPDX declarations and copyright text in the installed distribution remain authoritative; the inventory does not replace preserving complete upstream notices in a production package.

## Frontend assets

- HTMX **2.0.8**, https://github.com/bigskysoftware/htmx — 0BSD. Unmodified minified upstream asset; notice in `app/static/vendor/htmx-LICENSE.txt`.
- Alpine CSP **3.15.0**, https://github.com/alpinejs/alpine — MIT. Unmodified CSP build; notice in `app/static/vendor/alpine-LICENSE.txt`. Includes upstream Vue reactivity code (MIT).
- Tailwind CSS / CLI **4.1.14**, https://github.com/tailwindlabs/tailwindcss — MIT. Development/build dependency; generated styles retain upstream banner. All application theme/layout styles are project-authored.
- Node dependency graph and integrity hashes are in `package-lock.json`. `scripts/build-assets.cjs` copies local assets; pages do not depend on a third-party CDN.

## Native development services

- MySQL Community **8.4 LTS** — GPL-2.0, separately installed Ubuntu system package. Tested native server 8.4.11.
- Redis **8.0.5** — separately installed Ubuntu package. Redis 8 offers AGPLv3/RSALv2/SSPLv1 licensing choices; production distribution/service licensing needs explicit review before commercial release. The application does not vendor the server binary.
- Mailpit **1.27.10**, https://github.com/axllent/mailpit — MIT, development mail capture only. Windows binary is downloaded into ignored local `instance/`, not committed or deployed. Download source/digest recorded under `output/native-downloads/`.

## Deferred dependencies

PydanticAI, PDF/OCR engines, Promptfoo, fonts and model weights have not yet been introduced; each requires version/license/security review at its implementation stage. No blanket commercial-use claim is made for future dependencies or a complete production distribution.

Dependency additions here implement the fixed stack: Flask-SQLAlchemy connects the prescribed ORM to Flask; PyMySQL RSA extra supports MySQL authentication; Flask-WTF handles CSRF; Python-dotenv supplies configuration; Tailwind/HTMX/Alpine implement the prescribed frontend. Build/dev tools add no additional production application framework. Audit output is local and time-specific, not proof of an entirely vulnerability-free system.
