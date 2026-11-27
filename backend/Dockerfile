# Build context: repository root (needs /backend, /frontend and /data)
# One image serves the API and the built UI from the same origin, so one login (DEMO_PASSWORD) covers both.

# ---- frontend
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_API_URL=""
RUN npm run build

# ---- api
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data DB_PATH=/app/var/draftmind.db CACHE_DIR=/app/var PORT=8000 \
    FRONTEND_DIST=/app/frontend-dist STL_DATA_DIR=/app/stl-data
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY data /app/data
COPY --from=web /web/dist /app/frontend-dist
RUN mkdir -p /app/var

# Optional: the official GRID hackathon data (licensed for the hackathon only; never in this repo).
# GRID_DATA=1 clones it from Cloud9's repository at build time and pre-builds the normalized cache.
# The raw match feeds are deleted afterwards; only the cache and the small index CSVs stay in the image.
ARG GRID_DATA=0
ARG STL_REPO=https://github.com/cloud9esports/stl-hackathon-2026-grid-starter.git
RUN if [ "$GRID_DATA" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends git ca-certificates && \
      git clone --depth 1 --filter=blob:none --sparse "$STL_REPO" "$STL_DATA_DIR" && \
      git -C "$STL_DATA_DIR" sparse-checkout set lol meta && \
      python -c "from app.adapters.grid_files import GridFilesAdapter as A; a=A(); a.load(); print(a.describe())" && \
      find "$STL_DATA_DIR/lol" -name '*.zst' -delete && rm -rf "$STL_DATA_DIR/.git" && \
      apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*; \
    fi

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health')"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
