# Office-Connect API — dev image (Python 3.12, matches the plan's runtime).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System libraries for OCR (Tesseract) and PDF export (WeasyPrint/GTK) are added
# when those modules land (DMWIS OCR; Reports & Analytics PDF). Left out of the
# base image for now to keep builds fast.
# RUN apt-get update && apt-get install -y --no-install-recommends \
#       tesseract-ocr libpango-1.0-0 libpangocairo-1.0-0 libcairo2 \
#     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY office_connect ./office_connect

EXPOSE 8001
# --proxy-headers: correct scheme/host behind a reverse proxy (Day-1 #10).
CMD ["uvicorn", "office_connect.main:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers", "--reload"]
