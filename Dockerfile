# One origin: Vite assets and the account-scoped FastAPI API.
FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig*.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN VITE_API_BASE_URL=/api npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AURA_ENV=production \
    AURA_EMBEDDING_DEVICE=cpu AURA_EMBEDDING_BATCH_SIZE=4 AURA_EMBEDDING_THREADS=2 \
    HF_HOME=/data/models AURA_STATIC_DIR=/app/dist PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-impress fonts-liberation ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir 'torch==2.8.0' --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY database ./database
COPY scripts ./scripts
COPY evaluation ./evaluation
COPY auth-migration.sql ./
COPY --from=frontend /build/dist ./dist
RUN groupadd --gid 10001 aura && useradd --uid 10001 --gid aura --home-dir /data --no-create-home aura \
    && mkdir -p /data/uploads /data/previews /data/models \
    && rm -rf /app/backend/uploads /app/backend/.local_storage \
    && ln -s /data/uploads /app/backend/uploads && ln -s /data/previews /app/backend/.local_storage \
    && chown -R aura:aura /data /app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:'+__import__('os').getenv('PORT','8000')+'/health',timeout=4)"
CMD ["python","-m","scripts.serve_production"]
