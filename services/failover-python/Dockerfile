FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LIFEOS_HOST=0.0.0.0 \
    LIFEOS_QUEUE_WORKER_ENABLED=false

WORKDIR /srv/lifeos

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY services/failover-python ./services/failover-python

USER 65532:65532
EXPOSE 8080

CMD ["python", "services/failover-python/server.py"]
