# VisFEM Deployment Guide

How to host VisFEM publicly on a Linux server:

- **Landing page** → `https://visfem.de/`
- **Web app** → `https://app.visfem.de/`

---

## 1. What you are deploying

Three pieces, all sitting behind **Caddy** (a small web server that also gets
free HTTPS certificates automatically):

```
                         ┌──────────────────────────────────────────┐
   Internet  ─────────►  │  Caddy  (HTTPS + routing by hostname)    │
                         └──┬───────────────────────┬───────────────┘
                            │                       │
                      visfem.de               app.visfem.de
                            │                       │
                  ┌─────────▼─────────┐   ┌─────────▼──────────────────┐
                  │ static landing    │   │ Docker container           │
                  │ page (HTML/CSS)   │   │ (the VisFEM web app)       │
                  │ /var/www/landing  │   │  one isolated session      │
                  │                   │   │  per browser connection    │
                  └───────────────────┘   └──────────┬─────────────────┘
                                                     │ reads (read-only)
                                            the mesh data in the repo's
                                            data/datasets/  folder
```

- The **landing page** is just static files. Its project tiles link to the app
  with `?model=<name>`, which makes the app open that model automatically.
- The **web app** runs in Docker. Each visitor gets their own backend process
  (no shared state between users); the built-in launcher allows up to 6
  concurrent sessions (can be modified).
- **Caddy** decides which of the two a request goes to based on the hostname,
  and handles all the HTTPS/certificate work for you.

---

## 2. Before you start: DNS

The landing page and the app are **two separate services on the same machine**.
Caddy tells them apart by hostname, so each needs its own name. That is why we
use a subdomain `app.visfem.de` for the app.

In your domain's DNS settings, create two records pointing at the server's
public IP address:

| Type | Name           | Value (example) |
|------|----------------|-----------------|
| A    | `visfem.de`    | `<server IP>`   |
| A    | `app.visfem.de`| `<server IP>`   |

(If the server also has an IPv6 address, add matching `AAAA` records.)

Check if both names resolve with:

```bash
dig +short visfem.de
dig +short app.visfem.de
```

Both should print the server's IP.

---

## 3. Install prerequisites (on the server)

SSH into the server as a user with `sudo`. Install Docker, the Compose plugin,
and Caddy.

### Docker + Compose
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER     # log out/in afterwards so this takes effect
docker compose version            # confirm the compose plugin is present
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
Caddy installs as a systemd service (`systemctl status caddy`) and reads its
config from `/etc/caddy/Caddyfile`.

---

## 4. Get the code

```bash
sudo mkdir -p /opt && cd /opt
sudo git clone https://github.com/matthiaskoenig/visfem
sudo chown -R $USER:$USER /opt/visfem
cd /opt/visfem
```

---

## 5. Stage the data (manual step)

Copy the real dataset files from the lab NAS into the repo's data folder.

---

## 6. Start the web app

```bash
cd /opt/visfem
docker compose -f compose.deploy.yml up -d --build
```

This builds the image and starts the container in the background. It listens
only on `127.0.0.1:8080` (not exposed to the internet directly — Caddy will
proxy to it).

The compose file already:
- mounts `./data` read-only into the container and points the app at it
  (`DATA_DIR`);
- sets `TRAME_USE_HOST: "wss://app.visfem.de"` so the live WebSocket
  connection uses the right public address.

> If you use a different app hostname than `app.visfem.de`, edit that one line
> in `compose.deploy.yml` and re-run the command above.

Check it came up:
```bash
docker compose -f compose.deploy.yml logs -f  
curl -I http://127.0.0.1:8080/                    # should return HTTP/1.1 200
```

---

## 7. Put up the landing page

```bash
sudo mkdir -p /var/www/landing
sudo cp -r /opt/visfem/deploy/landing/. /var/www/landing/
```

The landing page is ready to serve as-is; its tiles already point at
`https://app.visfem.de/?model=...`.

---

## 8. Configure Caddy

Back up any existing config, then write the new one:

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

Validate and reload:
```bash
caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

That is all that is needed for HTTPS — Caddy automatically obtains and renews
Let's Encrypt certificates for both names, as long as DNS (step 2) points here.

---

## 9. Verify

If something is off, the app logs are the place to look:
```bash
cd /opt/visfem && docker compose -f compose.deploy.yml logs -f
```

---

## 10. Day-to-day operation

```bash
cd /opt/visfem
docker compose -f compose.deploy.yml up -d        # start / apply changes
docker compose -f compose.deploy.yml restart      # restart
docker compose -f compose.deploy.yml logs -f      # tail logs
docker compose -f compose.deploy.yml down         # stop
```

- The container is set to `restart: unless-stopped`, so it comes back
  automatically after a reboot or crash.
- **Concurrency** — how many visitors can use the app at once:
  - The limit lives in **`setup/launcher.json`**, in the `resources` →
    `port_range` field. The trame launcher gives each visitor their own backend
    process on one port from this range, so the number of ports = the number of
    simultaneous sessions. The default `[9001, 9006]` means **5 sessions**.
  - To allow more, widen the range (e.g. `[9001, 9020]` for 20) and **rebuild
    the image** — `launcher.json` is baked in at build time:
    ```bash
    docker compose -f compose.deploy.yml up -d --build
    ```
  - `"timeout": 60` in the same file reclaims idle sessions after 60 s, freeing
    their port for the next visitor.
  - **Size the range to available RAM**: each active session is
    ≈ 313 MB (see below), so 6 sessions ≈ 1.9 GB peak and 20 ≈ 6 GB+.


## Appendix: password-protect during testing (optional)

If you want the site private before the public launch, add a password prompt
with Caddy's built-in basic auth.

Generate a hashed password:
```bash
caddy hash-password --plaintext 'choose-a-password'
```

Then wrap either or both site blocks with a `basic_auth` directive, e.g.:
```caddy
app.visfem.de {
	basic_auth {
		visfem <paste-the-hash-here>
	}
	reverse_proxy 127.0.0.1:8080
}
```
Reload Caddy (`sudo systemctl reload caddy`). Remove the `basic_auth` block to
go public again.

---

## Appendix: what was prepared in the repo for deployment

For reference, the deployment-specific changes already committed:

- **`Dockerfile`** — uses the `kitware/trame:uv` base image (Python 3.13) and
  installs OSMesa libraries so 3D rendering works on a server without a GPU.
- **`src/visfem/engine/discovery.py`** — reads a `DATA_DIR` environment
  variable to locate `data/datasets/`. 
- **`src/visfem/app.py`** + **`src/visfem/ui/layout.py`** — support the
  `?model=<key>` URL parameter (used by the landing-page tiles) to auto-open a
  dataset, and make full-mesh preloading opt-in (`VISFEM_PRELOAD=1`) so the
  idle container stays light.
- **`compose.deploy.yml`** — the production Docker Compose file.
- **`deploy/landing/`** — the ready-to-serve landing page.
