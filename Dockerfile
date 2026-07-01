FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup -S appgroup && adduser -S -G appgroup appuser

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app/ ./app/

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.server:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--access-log"]
