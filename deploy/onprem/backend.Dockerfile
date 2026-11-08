# Backend image. Build context is the repository root (see docker-compose.yml).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Run as an unprivileged user.
RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
# Database migrations run automatically at startup (app/db/migrate.py).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
