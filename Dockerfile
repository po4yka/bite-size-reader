# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY bot.py ./

VOLUME ["/data"]
ENV DB_PATH=/data/app.db \
    LOG_LEVEL=INFO \
    REQUEST_TIMEOUT_SEC=60

CMD ["python", "-u", "bot.py"]

