# Flask status node image. The same image is started multiple times by Compose.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached when only code changes.
COPY PoC/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY PoC/backend/node.py ./node.py

# Directory for the per-node SQLite file; mounted as a named volume in Compose.
RUN mkdir -p /data
ENV DB_PATH=/data/status.db

EXPOSE 5000

# Compose overrides NODE_NAME / PEERS / PORT via environment variables per node.
CMD ["python", "node.py"]
