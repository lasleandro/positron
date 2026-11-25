# pode abrir (positron) image for Azure App Service (single container).
# Adapted from agenda_ai's Dockerfile: multi-stage build, non-root user, role-based entrypoint.
#
# Roles (ROLE env var, see scripts/deploy/entrypoint.sh):
#   platform (default) - apply migrations, run the email worker (auto-restarted) and Gunicorn
#   web                - Gunicorn only
#   mailer             - email worker only
#   migrate            - apply migrations and exit
#
# Build from the repository root:
#   docker build -t podeabrir .

# ---------------------------------------------------------------------------
# Stage 1 - build the React SPA (static, CSP-friendly bundle)
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/scripts/ scripts/
RUN npm ci
# vite.config.ts reads ../VERSION (shown under the login card)
COPY VERSION /src/VERSION
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 - runtime: Django API + built SPA, served by Gunicorn
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Sao_Paulo \
    PORT=8000

# ca-certificates: TLS verify-full to Azure PostgreSQL and SMTP; curl: container healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY manage.py VERSION ./
COPY exams/ exams/
COPY scripts/deploy/ scripts/deploy/
COPY --from=frontend-build /src/frontend/dist/ frontend/dist/

# Non-root user with a home directory (Gunicorn writes its control socket there).
RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["/bin/bash", "scripts/deploy/healthcheck.sh"]

ENTRYPOINT ["/bin/bash", "scripts/deploy/entrypoint.sh"]
