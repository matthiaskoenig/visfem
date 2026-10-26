# Deployment

Host VisFEM on a Linux server:

- Landing page  → `https://visfem.de/`
- Web app       → `https://app.visfem.de/`

The setup is three pieces behind Caddy: a static landing page, the app in Docker, and Caddy routing by hostname and handling HTTPS.

Until the server is live, `visfem.de` is served by GitHub Pages: the `documentation` workflow publishes the interim landing page of [`deploy/pages/`](https://github.com/matthiaskoenig/visfem/tree/develop/deploy/pages) at the root and this documentation below [`/docs/`](https://visfem.de/docs/), see [Documentation](development.md#documentation). Section 2 repoints the `visfem.de` DNS record from GitHub Pages to the server IP. Before that switch, move the custom domain of the GitHub Pages site to `docs.visfem.de` and set `site_url` in `zensical.toml` accordingly, so the documentation stays online.

---

## 1. Overview

```
                         ┌──────────────────────────────────────────┐
   Internet  ─────────►  │  Caddy  (HTTPS + routing by hostname)     │
                         └──┬───────────────────────┬────────────────┘
                            │                        │
                      visfem.de                app.visfem.de
                            │                        │
                  ┌─────────▼─────────┐   ┌──────────▼─────────────────┐
                  │ static landing    │   │ Docker container "visfem"  │
                  │ /var/www/landing  │   │ (the VisFEM web app)       │
                  └───────────────────┘   └──────────┬─────────────────┘
                                                      │ reads (read-only)
                                             /opt/visfem/data/datasets/
```

- Landing page: static files ([`deploy/landing/`](https://github.com/matthiaskoenig/visfem/tree/develop/deploy/landing)). Tiles link to the app with `?model=<name>` to open a specific model.
- Web app: Docker container `visfem`. Each visitor gets an isolated backend process; concurrency is set in [`setup/launcher.json`](https://github.com/matthiaskoenig/visfem/blob/develop/setup/launcher.json) (section 9).
- Caddy: routes by hostname and manages Let's Encrypt certificates.

Requirements:

- Linux server (Ubuntu/Debian assumed) with a public IP and `sudo`.
- Control over the `visfem.de` DNS records.
- Ports 80 and 443 open (80 for the certificate challenge, 443 for HTTPS):
  ```bash
  sudo ufw allow 80,443/tcp    # only if ufw is in use
  ```
- The dataset files (meshes), which live on the lab NAS. Section 5 stages them.

---

## 2. DNS

Create two A records pointing at the server IP, one per hostname Caddy routes on:

| Type | Name             | Value           |
|------|------------------|-----------------|
| A    | `visfem.de`      | `<server IP>`   |
| A    | `app.visfem.de`  | `<server IP>`   |

If `visfem.de` points at GitHub Pages, change it to the server IP. `app.visfem.de` is new. Add matching `AAAA` records if the server has IPv6.

Caddy issues certificates once both names resolve to the server. Verify:

```bash
dig +short visfem.de
dig +short app.visfem.de
```

Both print the server IP once DNS has propagated.

---

## 3. Server prerequisites

### Docker + Compose

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER     # grants $USER docker access; re-login to apply
```

Re-login (or `newgrp docker`), then confirm:

```bash
docker --version
docker compose version
```

### Caddy

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Caddy runs as a systemd service and reads `/etc/caddy/Caddyfile` (written in section 7). Confirm with `systemctl status caddy`.

The Caddyfile of section 7 rate limits the session requests with the [caddy-ratelimit](https://github.com/mholt/caddy-ratelimit) module, which the Caddy package does not include. Build a Caddy with the module in Docker, which needs no Go toolchain on the server, and let the package run it instead of its own binary ([custom builds of the Debian package](https://caddyserver.com/docs/build#package-support-files-for-custom-builds-for-debianubunturaspbian)):

```bash
cd /tmp
docker run --rm -v "$PWD:/out" caddy:2.11.7-builder xcaddy build v2.11.7 \
  --with github.com/mholt/caddy-ratelimit@5625512f24f6f59d6f64fb3aafe5eecff0b286db \
  --output /out/caddy
sudo dpkg-divert --divert /usr/bin/caddy.default --rename /usr/bin/caddy
sudo mv ./caddy /usr/bin/caddy.custom
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.default 10
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.custom 50
sudo systemctl restart caddy
caddy list-modules | grep rate_limit     # http.handlers.rate_limit
```

The module is pinned to a commit, it has no recent release. A package upgrade only replaces `/usr/bin/caddy.default`; for a new Caddy version, build again with the new version in the image tag and the `xcaddy build` argument, then `sudo mv ./caddy /usr/bin/caddy.custom` and restart.

---

## 4. Code checkout

```bash
sudo mkdir -p /opt && cd /opt
sudo git clone https://github.com/matthiaskoenig/visfem
sudo chown -R $USER:$USER /opt/visfem
cd /opt/visfem
```

All later commands run from `/opt/visfem`.

---

## 5. Dataset files

Copy the dataset files from the lab NAS into the repo's data folder.

```bash
# Set the source to the NAS mount or host; trailing slashes copy folder contents into the target folder.
rsync -av <nas>:/path/to/data/datasets/  /opt/visfem/data/datasets/
```

Stage all datasets. The allowlist in `compose.deploy.yml` (section 6) selects the public subset.

---

## 6. Web app

```bash
cd /opt/visfem
docker compose -f compose.deploy.yml up -d --build
```

This reads [`compose.deploy.yml`](https://github.com/matthiaskoenig/visfem/blob/develop/compose.deploy.yml) and:

- builds the image `visfem:local` from the [`Dockerfile`](https://github.com/matthiaskoenig/visfem/blob/develop/Dockerfile);
- starts the container `visfem` on `127.0.0.1:8080`, the loopback port Caddy proxies to;
- mounts `./data` read-only and points the app at it via `DATA_DIR`;
- sets `TRAME_USE_HOST: "wss://app.visfem.de"`, the public address the browser opens its WebSocket to;
- restricts the public app to the datasets listed in `VISFEM_DATASETS`, a comma-separated allowlist of dataset keys (a key is a descriptor's `.json` filename stem, e.g. `heart`). Unlisted datasets stay hidden;
- bounds the mesh cache of every session with `VISFEM_MESH_CACHE_MB` and the memory, processor time and processes of the container with `mem_limit`, `cpus` and `pids_limit` (section 9).

Confirm it is up:

```bash
docker compose -f compose.deploy.yml ps        # STATUS: Up
curl -I http://127.0.0.1:8080/                 # HTTP/1.1 200
```

Change a setting by editing [`compose.deploy.yml`](https://github.com/matthiaskoenig/visfem/blob/develop/compose.deploy.yml) and re-running `docker compose -f compose.deploy.yml up -d`.

---

## 7. Caddy configuration

Copy the landing page to Caddy's web root:

```bash
sudo mkdir -p /var/www/landing
sudo cp -r /opt/visfem/deploy/landing/. /var/www/landing/
```

The landing page ([`deploy/landing/`](https://github.com/matthiaskoenig/visfem/tree/develop/deploy/landing)) ships with tiles that point at `https://app.visfem.de/?model=...`.

Back up any existing Caddy config, then write the new one:

```bash
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
visfem.de {
	root * /var/www/landing
	file_server
}

app.visfem.de {
	# every page load starts a session process with a POST to the launcher at
	# /paraview/; a client (an IPv4 address or an IPv6 /64) may start 4 per
	# minute, Caddy answers more with 429 and a Retry-After header
	rate_limit {
		zone sessions {
			match {
				method POST
				path /paraview /paraview/*
			}
			key {remote_host}
			ipv6_prefix 64
			events 4
			window 1m
		}
	}

	# the trame client reads its connection settings from the URL as well; a
	# link must not point a visitor's browser at another session server
	@session_override expression `{query.sessionURL} != "" || {query.sessionManagerURL} != "" || {query.secret} != ""`
	respond @session_override "Bad Request" 400

	header {
		# the browser connects to this host only, the app is never framed
		Content-Security-Policy "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "strict-origin-when-cross-origin"
		-Server
	}
	reverse_proxy 127.0.0.1:8080
}
EOF
```

This serves the static landing page on `visfem.de` and forwards `app.visfem.de` traffic to the app container. The app block limits how many sessions a client can start, rejects links which override the session settings of the trame client and sends the security headers; `connect-src 'self'` keeps the browser from opening a WebSocket to any other host. Validate and load it:

```bash
caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy obtains and renews Let's Encrypt certificates for both names automatically, provided the section 2 DNS points at this server and ports 80/443 are open.

---

## 8. Verification

- `https://visfem.de/` shows the landing page with dataset tiles.
- `https://app.visfem.de/` loads the app; selecting a dataset renders its mesh.
- Clicking a landing-page tile opens the app with that model loaded.

The first request to each hostname may take a few seconds while Caddy fetches the certificate. Logs:

```bash
cd /opt/visfem && docker compose -f compose.deploy.yml logs -f    # app
sudo journalctl -u caddy -f                                       # Caddy
```

---

## 9. Operation

Run from `/opt/visfem`:

```bash
docker compose -f compose.deploy.yml up -d         # start / apply config changes
docker compose -f compose.deploy.yml restart       # restart
docker compose -f compose.deploy.yml logs -f       # logs
docker compose -f compose.deploy.yml down          # stop
docker compose -f compose.deploy.yml up -d --build # rebuild after code/config changes
```

- `restart: unless-stopped` brings the container back after a reboot or crash.
- Update the code with `git pull`, then rebuild (`docker compose -f compose.deploy.yml up -d --build`). Staged data and the landing page stay in place.
- Concurrency: set in [`setup/launcher.json`](https://github.com/matthiaskoenig/visfem/blob/develop/setup/launcher.json), field `resources` → `port_range`. Each visitor holds one port from the range; the port count is the session cap. The default `[9001, 9006]` is 6 sessions. Widening the range (e.g. `[9001, 9020]`) needs a rebuild: `launcher.json` is baked into the image. `"timeout": 60` in the same file is how long the launcher waits for a new session to start. A session ends 30 seconds after its last client disconnected, set by `--timeout` in [`setup/apps.yml`](https://github.com/matthiaskoenig/visfem/blob/develop/setup/apps.yml); a session which is requested but never connected holds its port for that long, too.
- Memory: every session is a process of its own, ~350 MB after the start, plus its mesh cache, plus the mesh on display. `VISFEM_MESH_CACHE_MB` in `compose.deploy.yml` bounds the cache of each session to 1024 MB, enough for the 30 keyframes of `heart_iv` (905 MB), the largest public series, to play from memory; a session viewing it takes ~1.3 GB, the static `tibia_simulation` ~1 GB. Beyond the limit the least recently used meshes are read from disk again. `mem_limit: 12g` caps the container at 6 sessions of up to ~1.7 GB, `cpus` and `pids_limit` cap its processor time and processes. Check `docker stats visfem` under real use; when widening the port range, raise `mem_limit` by ~1.7 GB per session and keep it below the memory of the server.
- Abuse: anybody can request sessions from the launcher without logging in. The `rate_limit` block of the Caddyfile (section 7) lets one client start 4 sessions per minute, counting an IPv4 address or an IPv6 /64 network as one client; as a session which is never connected frees its port after 30 seconds, one client holds at most 4 of the 6 ports at a time and 2 on average. Requests from many addresses can still take every port; then put the site behind basic auth (Appendix A) until the requests stop.

---

## Appendix A: private site during testing

Password-protect with Caddy basic auth. Generate a hash:

```bash
caddy hash-password --plaintext 'choose-a-password'
```

Wrap either site block in `/etc/caddy/Caddyfile` with `basic_auth`:

```caddy
app.visfem.de {
	basic_auth {
		visfem <paste-the-hash-here>
	}
	reverse_proxy 127.0.0.1:8080
}
```

Reload Caddy (`sudo systemctl reload caddy`). Remove the block and reload to go public.

---

## Appendix B: deployment files in the repo

- [`Dockerfile`](https://github.com/matthiaskoenig/visfem/blob/develop/Dockerfile): builds the app image from the `kitware/trame:uv` base (Python 3.14) and installs OSMesa for software 3D rendering.
- [`compose.deploy.yml`](https://github.com/matthiaskoenig/visfem/blob/develop/compose.deploy.yml): the production Compose file (image name, port binding, data mount, the resource caps and the `DATA_DIR` / `TRAME_USE_HOST` / `VISFEM_DATASETS` / `VISFEM_MESH_CACHE_MB` settings).
- [`setup/launcher.json`](https://github.com/matthiaskoenig/visfem/blob/develop/setup/launcher.json): the trame launcher config (concurrency `port_range`, start `timeout`), baked into the image at build.
- [`setup/apps.yml`](https://github.com/matthiaskoenig/visfem/blob/develop/setup/apps.yml): the session command of the launcher, `visfem` with the idle `--timeout`.
- [`setup/requirements.txt`](https://github.com/matthiaskoenig/visfem/blob/develop/setup/requirements.txt): the pinned dependencies of the image, exported from `uv.lock`, see [Deployment requirements](development.md#deployment-requirements).
- [`deploy/landing/`](https://github.com/matthiaskoenig/visfem/tree/develop/deploy/landing): the static landing page.
- `src/visfem/engine/discovery.py`: reads `DATA_DIR` and the `VISFEM_DATASETS` allowlist.
- `src/visfem/log.py`: reads `VISFEM_LOG_LEVEL` (default `WARNING`), the level of the container log.
- `src/visfem/app.py` and `src/visfem/ui/layout.py`: handle the `?model=<key>` URL parameter and on-demand mesh loading.
