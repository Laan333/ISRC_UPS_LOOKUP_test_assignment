# Nginx image (Docker)

Build context is **this directory** (`./nginx`). These files must be present when you run `docker compose build`:

- `Dockerfile`
- `http-only.conf`
- `https.conf.envsubst`
- `docker-entrypoint.d/09-gen-nginx-conf.sh`

If the build fails with `COPY ... not found`, your checkout is missing one of the above — sync with the repository (e.g. `git pull`).
