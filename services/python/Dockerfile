FROM python:3.11-slim

WORKDIR /app

# System deps for torch compilation fallback
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download BGE-M3 model during build (avoids cold start)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"

# Copy Python service source
COPY services/python/ .

# Copy KB module (at project root level, not under services/python/)
COPY kb/ /app/kb/

# Copy seed scripts (needed for `docker compose run --rm seed`)
COPY scripts/seed_kb.py scripts/gen_seeds.py /app/scripts/

COPY services/python/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
