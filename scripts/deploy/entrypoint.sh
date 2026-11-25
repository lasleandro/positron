#!/usr/bin/env bash
# Container entrypoint (pattern from agenda_ai). One image, several roles, selected by $ROLE.
set -euo pipefail

: "${ROLE:=platform}"
: "${PORT:=8000}"
: "${GUNICORN_WORKERS:=2}"
: "${GUNICORN_THREADS:=4}"

echo "Starting pode abrir $(cat VERSION 2>/dev/null || echo '?') role=${ROLE} (APP_ENV=${APP_ENV:-unset})"

# Optional database readiness wait: set DB_WAIT_HOST (and DB_WAIT_PORT, default 5432).
if [[ -n "${DB_WAIT_HOST:-}" ]]; then
  echo "Waiting for database ${DB_WAIT_HOST}:${DB_WAIT_PORT:-5432} ..."
  for i in $(seq 1 30); do
    if timeout 2 bash -c "</dev/tcp/${DB_WAIT_HOST}/${DB_WAIT_PORT:-5432}" 2>/dev/null; then
      echo "Database is reachable"
      break
    fi
    echo "... retry ${i}"
    sleep 2
  done
fi

run_gunicorn() {
  # Azure's front end terminates TLS and sets X-Forwarded-Proto (SECURE_PROXY_SSL_HEADER).
  exec gunicorn exams.wsgi:application \
    --bind "0.0.0.0:${PORT}" --workers "${GUNICORN_WORKERS}" --threads "${GUNICORN_THREADS}" \
    --timeout 60 --forwarded-allow-ips="*" --access-logfile - --error-logfile -
}

mailer_forever() {
  # Keep the outbox drained even if the worker crashes (Gunicorn stays PID 1).
  while true; do
    python manage.py send_emails || true
    echo "email worker exited; restarting in 5s" >&2
    sleep 5
  done
}

case "${ROLE}" in
  platform)
    python manage.py migrate --noinput
    mailer_forever &
    run_gunicorn
    ;;
  web)
    run_gunicorn
    ;;
  mailer)
    exec python manage.py send_emails
    ;;
  migrate)
    exec python manage.py migrate --noinput
    ;;
  *)
    echo "Unknown ROLE: ${ROLE}" >&2
    exit 1
    ;;
esac
