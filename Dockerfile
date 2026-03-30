FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY run.py ./

ENV PYTHONUNBUFFERED=1
ENV SPACE_TRAFFIC_API_KEY=space-demo-key
ENV SPACE_TRAFFIC_DB_PATH=/data/space_traffic.db

RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

CMD ["python", "run.py"]
