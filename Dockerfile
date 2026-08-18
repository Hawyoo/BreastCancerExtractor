FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.116,<1" \
    "httpx>=0.28,<1" \
    "pillow>=11,<13" \
    "pydantic-settings>=2.10,<3" \
    "python-multipart>=0.0.20,<1" \
    "pyyaml>=6,<7" \
    "uvicorn[standard]>=0.35,<1"

COPY app ./app
COPY knowledge ./knowledge

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /runtime/database /models/llm \
    && chown -R app:app /runtime /models/llm

USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
