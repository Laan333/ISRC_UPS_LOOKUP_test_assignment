FROM nginx:1.27-alpine

RUN apk add --no-cache gettext \
    && rm -f /etc/nginx/templates/default.conf.template

# Configs live next to this Dockerfile so `docker compose build` always sees them (context: ./nginx).
COPY http-only.conf /opt/nginx/http-only.conf
COPY https.conf.envsubst /opt/nginx/https.conf.envsubst
COPY docker-entrypoint.d/99-gen-nginx-conf.sh /docker-entrypoint.d/99-gen-nginx-conf.sh
RUN chmod +x /docker-entrypoint.d/99-gen-nginx-conf.sh
