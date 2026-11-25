# Stage 1: build the React SPA (static, CSP-friendly bundle).
FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/scripts/ scripts/
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Django API that also serves the built SPA.
FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY manage.py ./
COPY exams/ exams/
COPY --from=frontend /src/frontend/dist/ frontend/dist/
USER app
EXPOSE 8000
# The email worker (invitations, password reset) runs beside Gunicorn in the same container.
CMD ["sh", "-c", "python manage.py migrate --noinput && (python manage.py send_emails &) && exec gunicorn exams.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2 --timeout 60"]
