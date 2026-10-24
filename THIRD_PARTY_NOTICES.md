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
| pydantic-ai-slim 1.107.9 / pydantic-graph | Typed model adapter and structured output | MIT |
| OpenAI Python SDK / HTTPX | Configured OpenAI-compatible transport | Apache-2.0 / BSD-3-Clause |
| cryptography 50.0.2 | Encrypt administrator-managed service credentials at rest | Apache-2.0 OR BSD-3-Clause |
| pdfplumber 0.11.10 / pdfminer.six | Bounded text PDF extraction | MIT |
| Pillow 13.0.0 | Image decoding and verification | MIT-CMU (HPND) |
| pypdfium2 5.14.0 | pdfplumber transitive PDF renderer; not directly invoked | Apache-2.0 / BSD-3-Clause; bundled PDFium has separate notices |

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

OCR engines, Promptfoo, fonts and model weights have not been introduced. No blanket commercial-use claim is made for future dependencies or a complete production distribution. Preserve pypdfium2/PDFium bundled third-party notices when packaging the installed distribution.

## Added development checks

- `pytest-cov` (MIT) and `coverage` (Apache-2.0) measure Python statement/branch coverage; no production runtime is added.
- `@playwright/test` (Apache-2.0) runs isolated browser workflows using the existing Node development runtime. Browser binaries are downloaded only to the local test cache and are not bundled with the application.

These additions address missing model transport, PDF parsing/image validation and reproducible end-to-end verification. Existing Flask/Pydantic dependencies cannot parse PDFs or operate a browser. The slim AI package enables only the prescribed OpenAI-compatible adapter; no second Agent framework is introduced. `scripts/inventory-dependencies.py` refreshes the runtime inventory from the lock-derived requirements file.

Dependency additions here implement the fixed stack: Flask-SQLAlchemy connects the prescribed ORM to Flask; PyMySQL RSA extra supports MySQL authentication; Flask-WTF handles CSRF; Python-dotenv supplies configuration; Tailwind/HTMX/Alpine implement the prescribed frontend. Build/dev tools add no additional production application framework. Audit output is local and time-specific, not proof of an entirely vulnerability-free system.
