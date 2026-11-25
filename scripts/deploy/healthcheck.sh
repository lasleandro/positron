#!/usr/bin/env bash
# Container HEALTHCHECK. Web roles must answer /healthz (database round trip); the mailer and
# migrate roles have no socket. Django only accepts the configured host, so send it.
set -euo pipefail

case "${ROLE:-platform}" in
  platform|web)
    host="${APP_ORIGIN#https://}"
    host="${host#http://}"
    exec curl -fsS -H "Host: ${host:-localhost}" "http://127.0.0.1:${PORT:-8000}/healthz"
    ;;
  *)
    exit 0
    ;;
esac
