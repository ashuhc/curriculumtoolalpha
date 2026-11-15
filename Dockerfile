# Single-container image: FastAPI serves both the API and the built website from
# one origin. Used by render.yaml (Render) and any host that runs one container.
#   docker build -t econ-scheduler . && docker run -p 8000:8000 -e DATABASE_URL=... econ-scheduler

# ---- Stage 1: build the React frontend --------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Empty = call the API on the same origin
ENV VITE_API_URL=""
RUN npm run build

# ---- Stage 2: Python API + static site --------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SCHEDULER_DATA_DIR=/app/data \
    STATIC_DIR=/app/static

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/backend/
COPY ECON_Enrollment.xlsx custom_faculty.json faculty_overloads.json teacher_preferences.csv TEACHER_PREFERENCES.py /app/data/
COPY --from=web /web/dist /app/static

RUN useradd --create-home app && chown -R app /app
USER app

# Render injects PORT (default 10000); locally it falls back to 8000.
EXPOSE 8000
CMD ["sh", "-c", "python seed_db.py && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
