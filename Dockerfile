FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONPATH=/app/src
ENV SPACE_TRAFFIC_API_KEY=space-demo-key
ENV SPACE_TRAFFIC_DB_PATH=/data/space_traffic.db

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY run.py ./
COPY docs ./docs

RUN useradd --create-home --uid 10001 appuser \
	&& mkdir -p /data \
	&& chown -R appuser:appuser /app /data

VOLUME ["/data"]

EXPOSE 8000

USER appuser

CMD ["python", "run.py"]
