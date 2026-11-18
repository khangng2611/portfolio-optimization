# Public HTTPS demo using Tailscale Funnel

Release `v0.1.0-demo.2` adds an explicit HTTPS deployment profile. Application code and release images are unchanged from `v0.1.0-demo.1`; the upgrade adds configuration and deployment validation only.

The Azure VM runs Tailscale Funnel → `http://127.0.0.1:3000` → Web/BFF → private Compose services. Visitors need only a browser. Run Funnel on the VPS, not the Mac. Azure's existing 23:00 Vietnam shutdown schedule stays enabled.

## Setup

Install Tailscale from its official Ubuntu repository, enable `tailscaled`, then run `sudo tailscale up --accept-dns=false --hostname=portfolio-demo` and complete the device login. Enable MagicDNS, HTTPS and Funnel for the node when prompted. The Personal plan supports noncommercial demos without buying a domain.

Use the exact HTTPS DNS name from `tailscale status --json` (Self.DNSName, without the trailing dot):

```bash
cd ~/portfolio-demo
export DEMO_PUBLIC_ORIGIN=https://portfolio-demo.YOUR-TAILNET.ts.net
python3.12 infra/local/bootstrap.py --refresh-demo
python3.12 scripts/check_private_demo.py --release v0.1.0-demo.2 --funnel-origin "$DEMO_PUBLIC_ORIGIN"
dc() { docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/public/compose.funnel.yaml "$@"; }
dc up -d --no-build --pull never --wait --wait-timeout 240
.venv-software/bin/python scripts/smoke_software.py
.venv-software/bin/python scripts/smoke_g2.py
sudo tailscale funnel --bg --https=443 http://127.0.0.1:3000
sudo tailscale funnel status
```

The override changes only `APP_ORIGIN`. The BFF derives Secure, HttpOnly, SameSite=Lax, __Host- cookies from the HTTPS origin and compares CSRF Origin exactly. `ALLOW_INSECURE_HTTP=true` remains necessary for internal HTTP Auth URLs; it does not prevent Secure cookies on the public origin. Do not turn it off without also moving internal Auth to HTTPS. Do not relax CSRF checks or rewrite the browser Origin to localhost.

Docker ports remain bound to loopback. Do not open Azure inbound 3000, database or broker ports. The new profile requires the exact HTTPS ts.net origin; running the old localhost checker against this profile should fail.

## Operation and verification

The owner runs the Mac's `deployment/start-demo.sh` to authenticate to Azure, start the VM if necessary, wait for SSH, validate the pinned release/profile, refresh synthetic data, wait for Compose health, run API/G2 smoke tests, ensure Funnel is enabled, and verify public HTTPS from the Mac. This requires no local port 3000 and no SSH port forwarding. After startup, the Mac can disconnect.

The demo login accounts remain private on the VPS. Visitors can register individual investor accounts; do not share operator credentials. Smoke tests create synthetic portfolios/proposals/targets. No trades or paid-provider calls are configured.

Before sharing, verify real browser registration/login, Secure cookies, CSRF and owner denial, EW/MVO/accept/history, expiry/logout, and Chat SSE over the public hostname. Initial browser receipts and sanitized screenshots should stay in the deployment folder, not Git. Internal smoke success alone is not public-HTTPS acceptance.

With `--bg`, Funnel resumes after a VM reboot while Tailscale remains authenticated. VM shutdown still makes the link unavailable. Stop/deallocate in Azure after a demo to save compute credit; disks and static IP remain billable. Closing a Mac terminal does not stop the VM or Funnel.

## Disable public access and rollback

```bash
sudo tailscale funnel reset
```

To restore the private profile without deleting data:

```bash
cd ~/portfolio-demo
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml up -d --no-build --pull never --wait --wait-timeout 240
```

Then use the prior SSH tunnel to localhost:3000. The base file's origin is still localhost. Never run `down -v`. Keep the previous release tag and runtime secrets. If restoring source to demo.1, also restore the previous Mac startup script, which pins that release. The new Mac script reports failure without shutting the VM down automatically.

References: [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel), [Funnel CLI and reboot persistence](https://tailscale.com/docs/reference/tailscale-cli/funnel), [Personal pricing](https://tailscale.com/pricing).
