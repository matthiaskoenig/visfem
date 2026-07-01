# VisFEM Deployment Guide

Host VisFEM on a Linux server:

- Landing page  → `https://visfem.de/`
- Web app       → `https://app.visfem.de/`

The setup is three pieces behind Caddy: a static landing page, the app in Docker,
and Caddy routing by hostname and handling HTTPS.

NOTE: `visfem.de` is currently served by GitHub Pages from the repo's `docs/` folder.
This deployment moves it onto the server, so section 2 repoints the `visfem.de` DNS
record from GitHub Pages to the server IP. Once live, the GitHub Pages site is
unused and can be retired.

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

- Landing page: static files ([`deploy/landing/`](deploy/landing/)). Tiles link to
  the app with `?model=<name>` to open a specific model.
- Web app: Docker container `visfem`. Each visitor gets an isolated backend process;
  concurrency is set in [`setup/launcher.json`](setup/launcher.json) (section 9).
- Caddy: routes by hostname and manages Let's Encrypt certificates.

Requirements:

- Linux server (Ubuntu/Debian assumed) with a public IP and `sudo`.
- Control over the `visfem.de` DNS records.
- Ports 80 and 443 open (80 for the certificate challenge, 443 for HTTPS):
  ```bash
  sudo ufw allow 80,443/tcp    # only if ufw is in use
  ```
- The dataset files (meshes). These are not in the git repo and are staged from the
  lab NAS in section 5.

---

## 2. DNS

The landing page and the app run on the same machine and are distinguished by
hostname, so each needs its own DNS name. Create two A records pointing at the
server IP:

| Type | Name             | Value           |
|------|------------------|-----------------|
| A    | `visfem.de`      | `<server IP>`   |
| A    | `app.visfem.de`  | `<server IP>`   |

If `visfem.de` currently points at GitHub Pages, change it to the server IP.
`app.visfem.de` is new. Add matching `AAAA` records if the server has IPv6.

Caddy cannot issue certificates until both names resolve to the server. Verify:

```bash
dig +short visfem.de
dig +short app.visfem.de
```

Both print the server IP once DNS has propagated.

---

## 3. Prerequisites (on the server)

### Docker + Compose

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER     # run docker without sudo; re-login to apply
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

Caddy runs as a systemd service and reads `/etc/caddy/Caddyfile` (written in
section 7). Confirm with `systemctl status caddy`.

---

## 4. Get the code

```bash
sudo mkdir -p /opt && cd /opt
sudo git clone https://github.com/matthiaskoenig/visfem
sudo chown -R $USER:$USER /opt/visfem
cd /opt/visfem
```

All later commands run from `/opt/visfem`.

---

## 5. Stage the dataset files

Copy the dataset files from the lab NAS into the repo's data folder.

```bash
# Adjust the source to the NAS mount/host. Trailing slashes copy contents into contents.
rsync -av <nas>:/path/to/data/datasets/  /opt/visfem/data/datasets/
```

Staging all datasets is fine even if the public site shows only some; the public
subset is controlled by an allowlist in `compose.deploy.yml` (section 6).

---

## 6. Start the web app

```bash
cd /opt/visfem
docker compose -f compose.deploy.yml up -d --build
```

This reads [`compose.deploy.yml`](compose.deploy.yml) and:

- builds the image `visfem:local` from the [`Dockerfile`](Dockerfile);
- starts the container `visfem`, listening only on `127.0.0.1:8080` (Caddy proxies
  to it; the port is not exposed to the internet);
- mounts `./data` read-only and points the app at it via `DATA_DIR`;
- sets `TRAME_USE_HOST: "wss://app.visfem.de"` so the browser opens its WebSocket to
  the correct public address;
- restricts the public app to the datasets listed in `VISFEM_DATASETS`, a
  comma-separated allowlist of dataset keys (a key is a descriptor's `.json`
  filename without the extension, e.g. `heart`). Datasets on disk but not listed
  stay hidden.

Confirm it is up:

```bash
docker compose -f compose.deploy.yml ps        # STATUS: Up
curl -I http://127.0.0.1:8080/                 # HTTP/1.1 200
```

Changing any of these settings later means editing that one file
([`compose.deploy.yml`](compose.deploy.yml)) and re-running
`docker compose -f compose.deploy.yml up -d`.
---

## 7. Configure Caddy

Copy the landing page to Caddy's web root:

```bash
sudo mkdir -p /var/www/landing
sudo cp -r /opt/visfem/deploy/landing/. /var/www/landing/
```

The landing page ([`deploy/landing/`](deploy/landing/)) is ready as-is; its tiles
already point at `https://app.visfem.de/?model=...`.

Back up any existing Caddy config, then write the new one:

```bash
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
visfem.de {
	root * /var/www/landing
	file_server
}

app.visfem.de {
	reverse_proxy 127.0.0.1:8080
}
EOF
```

This serves the static landing page on `visfem.de` and forwards `app.visfem.de`
traffic to the app container. Validate and load it:

```bash
caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy obtains and renews Let's Encrypt certificates for both names automatically,
provided the section 2 DNS points at this server and ports 80/443 are open.

---

## 8. Verify

- `https://visfem.de/` shows the landing page with dataset tiles.
- `https://app.visfem.de/` loads the app; selecting a dataset renders its mesh.
- Clicking a landing-page tile opens the app with that model loaded.

The first request to each hostname may take a few seconds while Caddy fetches the
certificate. Logs:

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

- The container uses `restart: unless-stopped`, so it returns after a reboot or
  crash.
- Update the code with `git pull`, then rebuild
  (`docker compose -f compose.deploy.yml up -d --build`). Staged data and the
  landing page are untouched.
- Concurrency: set in [`setup/launcher.json`](setup/launcher.json), field
  `resources` → `port_range`. Each visitor uses one port from the range, so the
  number of ports equals the number of simultaneous sessions. The default
  `[9001, 9006]` is 6 sessions. Widening the range (e.g. `[9001, 9020]`) requires a
  rebuild, since `launcher.json` is baked into the image. `"timeout": 60` in the
  same file reclaims an idle session after 60 seconds. Memory scales with sessions
  and dataset size; check `docker stats visfem` under real use before widening.

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

Reload Caddy (`sudo systemctl reload caddy`). Remove the block and reload to go
public.

---

## Appendix B: deployment files in the repo

- [`Dockerfile`](Dockerfile): builds the app image from the `kitware/trame:uv` base
  (Python 3.13) and installs OSMesa for GPU-less 3D rendering.
- [`compose.deploy.yml`](compose.deploy.yml): the production Compose file (image
  name, port binding, data mount, and the `DATA_DIR` / `TRAME_USE_HOST` /
  `VISFEM_DATASETS` settings).
- [`setup/launcher.json`](setup/launcher.json): the trame launcher config
  (concurrency `port_range`, idle `timeout`), baked into the image at build.
- [`deploy/landing/`](deploy/landing/): the static landing page.
- `src/visfem/engine/discovery.py`: reads `DATA_DIR` and the `VISFEM_DATASETS`
  allowlist.
- `src/visfem/app.py` + `src/visfem/ui/layout.py`: handle the `?model=<key>` URL
  parameter and on-demand mesh loading.
