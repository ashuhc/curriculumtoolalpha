# Build context: repository root (needs the source data files for seeding).
#   docker build -f backend/Dockerfile -t econ-scheduler-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SCHEDULER_DATA_DIR=/app/data

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/backend/
# Source files consumed by seed_db.py
COPY ECON_Enrollment.xlsx custom_faculty.json faculty_overloads.json teacher_preferences.csv TEACHER_PREFERENCES.py /app/data/

RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# seed_db.py only fills empty tables, so it is safe on every start.
# One worker: the WebSocket hub is in-process (see realtime.py).
CMD ["sh", "-c", "python seed_db.py && exec uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
