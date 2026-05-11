FROM nginx:1.27-alpine

RUN apk add --no-cache gettext \
    && rm -f /etc/nginx/templates/default.conf.template

COPY build/http-only.conf /opt/nginx/http-only.conf
COPY build/https.conf.envsubst /opt/nginx/https.conf.envsubst
COPY docker-entrypoint.d/99-gen-nginx-conf.sh /docker-entrypoint.d/99-gen-nginx-conf.sh
RUN chmod +x /docker-entrypoint.d/99-gen-nginx-conf.sh
