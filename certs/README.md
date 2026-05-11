# TLS certificates for nginx (optional)

When `NGINX_SSL_ENABLED=true` in `.env`, Docker mounts this directory to `/etc/nginx/ssl` inside the nginx container.

Expected file names (defaults; override with `NGINX_SSL_CERT` / `NGINX_SSL_KEY`):

- `fullchain.pem` — full certificate chain (e.g. Let’s Encrypt `fullchain.pem`)
- `privkey.pem` — private key

Do **not** commit real private keys. Keep PEM files local or load them from a secret store in production.

### Let’s Encrypt (example)

On the host, after obtaining certs (Certbot, acme.sh, etc.), copy or symlink them here as `fullchain.pem` and `privkey.pem`, or set `NGINX_SSL_CERT` / `NGINX_SSL_KEY` to the paths **inside the container** (under `/etc/nginx/ssl/...` if you mount this folder).

### Local development

Use `mkcert` or a self-signed pair for `localhost`, then place the PEM files in this directory with the names above.
