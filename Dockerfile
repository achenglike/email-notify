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

CMD ["gunicorn", "-w", "1", "--threads", "4", \
     "-b", "0.0.0.0:8000", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "app.server:app"]
