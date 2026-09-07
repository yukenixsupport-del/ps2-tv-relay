FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY relay.py relay_channels.json ./

ENV LISTEN_HOST=0.0.0.0
ENV PORT=80
ENV PUBLIC_BASE_URL=http://127.0.0.1

EXPOSE 80
CMD ["python3", "relay.py"]
