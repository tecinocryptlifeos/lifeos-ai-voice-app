FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LIFEOS_HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

RUN groupadd --gid 10001 lifeos \
    && useradd \
       --uid 10001 \
       --gid lifeos \
       --create-home \
       --shell /usr/sbin/nologin \
       lifeos

COPY requirements.txt ./

RUN pip install \
    --no-cache-dir \
    -r requirements.txt

COPY --chown=lifeos:lifeos . .

USER lifeos

EXPOSE 8080

CMD ["python", "app/lifeos_voice_server.py"]
