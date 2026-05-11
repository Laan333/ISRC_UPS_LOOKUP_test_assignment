#!/bin/sh
set -e
# Runs before 10-listen-on-ipv6-by-default.sh so the stock default.conf is replaced first,
# then the IPv6 helper adjusts our generated file.

enabled="${NGINX_SSL_ENABLED:-false}"
case "$enabled" in
  true|True|TRUE|1|yes|Yes|YES)
    cert="${NGINX_SSL_CERT:-/etc/nginx/ssl/fullchain.pem}"
    key="${NGINX_SSL_KEY:-/etc/nginx/ssl/privkey.pem}"
    if [ ! -f "$cert" ] || [ ! -f "$key" ]; then
      echo "nginx: NGINX_SSL_ENABLED is set but certificate files are missing:" >&2
      echo "  NGINX_SSL_CERT=$cert" >&2
      echo "  NGINX_SSL_KEY=$key" >&2
      echo "Mount host directory with PEM files (see certs/README.md)." >&2
      exit 1
    fi
    export NGINX_SSL_CERT="$cert"
    export NGINX_SSL_KEY="$key"
    # Only substitute cert paths; $$ in the template becomes $ for nginx variables.
    envsubst '${NGINX_SSL_CERT} ${NGINX_SSL_KEY}' </opt/nginx/https.conf.envsubst >/etc/nginx/conf.d/default.conf
    ;;
  *)
    cp /opt/nginx/http-only.conf /etc/nginx/conf.d/default.conf
    ;;
esac
