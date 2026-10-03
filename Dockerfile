# Open PMS: one small container. Data lives in the /data volume.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENPMS_INSTANCE=/data \
    OPENPMS_DATABASE=/data/openpms.db

RUN useradd --create-home --uid 10001 openpms && mkdir /data && chown openpms /data
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY openpms ./openpms
RUN pip install --no-cache-dir ".[server]"

USER openpms
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "openpms:create_app()"]
