# Office-Connect API — dev image (Python 3.12, matches the plan's runtime).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# postgresql-client-16: pg_dump/pg_restore/createdb/dropdb for the backup +
# restore-drill (Increment 2). The client MAJOR must MATCH the server
# (postgres:16-alpine): a newer pg_dump (17) emits SET commands (e.g.
# transaction_timeout) that a PG16 server rejects on restore, so "client newer"
# is NOT safe here — pin to 16 from the PostgreSQL PGDG apt repo (the slim base
# is currently Debian trixie, whose stock client is 17). The repo suite is
# derived from the base image's own codename so a future base bump won't wedge
# it. RULE: bump the `db` image tag and this client package together
# (docs/standards/tech-stack.md §3).
#
# OCR (Tesseract) libraries are added when DTWIS OCR lands.
#
# WeasyPrint (core-service #8, Stage C R-5) is pure Python but binds Pango at
# RUNTIME via cffi, so the native stack must exist in the image:
#   libpango-1.0-0 / libpangoft2-1.0-0 — text shaping + layout (pulls glib,
#     harfbuzz, fontconfig, freetype). WeasyPrint >= 53 has its own PDF writer,
#     so cairo and gdk-pixbuf are deliberately NOT installed, and raster images
#     go through Pillow, which already ships self-contained wheels.
#   libffi8 — the cffi runtime WeasyPrint calls Pango through.
#   fonts-dejavu-core — python:*-slim ships NO fonts at all; without a font
#     family every generated PDF renders as blank boxes. The print stylesheet
#     therefore names DejaVu explicitly rather than trusting a system default.
# All three Python services (app / worker / beat) share this image, so the layer
# lands once. RULE: WeasyPrint runs only inside this container — never on the
# Windows host (docs/standards/tech-stack.md §3).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
         libpango-1.0-0 libpangoft2-1.0-0 libffi8 fonts-dejavu-core \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
         -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
         > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY office_connect ./office_connect

RUN chmod +x /app/scripts/entrypoint.sh

EXPOSE 8001
# entrypoint.sh runs the dev-only, env-gated boot migration (OC_MIGRATE_ON_BOOT)
# then execs the service command below. Prod leaves the flag OFF and runs the
# explicit `alembic upgrade head` deploy step instead (foundation.md §3).
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
# --proxy-headers: correct scheme/host behind a reverse proxy (Day-1 #10).
CMD ["uvicorn", "office_connect.main:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers", "--reload"]
