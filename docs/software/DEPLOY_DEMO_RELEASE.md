# Deploy a demo release in one command

The Mac entry point is `scripts/deploy_demo.py TAG`; the installed convenience wrapper is `deployment/deploy-demo.sh TAG`. Run against a **clean checkout of that committed tag**. Uncommitted files, version strings that are not Git tags, and tag/HEAD mismatches are rejected. The default installed source checkout is recorded in `deployment/source-repo.txt`; override with `--repo /absolute/path/to/checkout` when working elsewhere.

Example, from the checkout containing the new code:

```bash
# Finish local changes, tests and commit first; choose a new version each time.
git tag -a v0.1.0-demo.9 -m 'Describe the release'
/Users/nguyenkhang/Documents/MASTER/Thesis/deployment/deploy-demo.sh v0.1.0-demo.9 --repo "$PWD"
```

The command runs the software suite, Web unit tests and typecheck locally. It starts the existing VM, checks that auto-shutdown remains Enabled at 23:00 Vietnam, transfers a Git bundle over the existing pinned SSH connection, and prepares the selected commit on the VPS. Expired Azure login can prompt for browser/MFA. Dependencies must already be prepared locally; use the project's existing software setup workflow.

## Transaction and maintenance window

1. Prepare a candidate checkout, isolated smoke Python environment and **release-tagged application images** before interrupting the current service. Prefetch external images if necessary. Build logs remain private on the VPS.
2. Capture exact previous container image IDs as local rollback tags. If image metadata has been removed while its container still exists, snapshot that container filesystem/config with `docker commit` before proceeding; the cold volume snapshot still protects its data. Validate Docker-managed volume ownership and available disk. Reject activation during 22:00–22:59 to protect the unchanged 23:00 shutdown.
3. Keep the same HTTPS hostname but show a maintenance page. Stop the whole project so DB, Redis and RabbitMQ are quiescent. Archive every existing project volume and `.generated`, retaining ownership/permissions (restore generated files with tar `-p`, independent of private umask); verify archives and SHA-256 hashes before activation.
4. Checkout the new commit, preserve existing secrets, refresh synthetic data and recreate containers using the release images. Run config validation, service health, the previous persisted G2 target receipt when available, Auth/Market/MVO/G2 smoke tests, and real BFF login/session/cookie/CSRF/origin/logout checks from the trusted VPS. Public TLS is checked separately from the Mac.
5. Restore the public proxy, verify HTTPS from the Mac with normal certificate validation, and only then write `~/demo-deploy/current.json`. If the Mac has a stale negative DNS cache, the probe can independently resolve the public hostname via Cloudflare DNS; TLS validation stays enabled.
6. Any exception after maintenance begins attempts rollback. Verify **all** backup hashes before clearing any volume, restore cold data/config, previous Git commit and exact old images, then start the old stack. A failed/corrupt restore does not report success. A durable journal remains for recovery.

Do not enter data or share the demo during this window; wait for `DEPLOY THÀNH CÔNG`. This is a coordinated demo deployment, not zero downtime. The final public probe briefly opens the new service; if that probe fails, restoring the pre-deploy snapshot discards any writes made during that interval. Backups are kept on the same VPS, not an independent disaster-recovery copy. OS/package upgrades, external/shared volume drivers and infrastructure topology changes require separate planning.

## Backup and recovery

On VPS:

- `~/demo-deploy/transactions/<id>/journal.json`: phases and archive checksums.
- `~/demo-deploy/transactions/<id>/*.tar.gz`: cold volume/config snapshots. **Contain credentials and user data; never commit or share them.**
- `~/demo-deploy/transactions/<id>/previous-images.json`: rollback image tags. Keep these images private; container-derived snapshots can contain runtime environment secrets. Never push them to a registry.
- `~/demo-deploy/current.json`: active release, commit, image override and smoke environment.
- `~/demo-deploy/pending.json`: incomplete deployment, if any.

The updated `start-demo.sh` reads this manifest instead of pinning demo.2. Start and deploy share a lock. Before starting the stack, it attempts recovery of an interrupted transaction. To recover explicitly after SSH loss/power failure, start the VM, SSH in and run:

```bash
python3.12 ~/demo-deploy/controller.py --remote-action recover
```

Recovery refuses to run while another deploy/start owns the lock. When a backup checksum is invalid or a volume path/driver is unsupported, keep maintenance enabled and inspect the private journal; do not delete state or manually run a different Compose profile.

No backup/image cleanup is automatic. Review successful releases and space before retiring old backups, candidate environments and rollback tags. Do not run `docker volume prune`, `docker image prune -a` or `down -v` while depending on retained rollback state.

## Manual service inspection

The active release uses an additional image override; a bare base+Funnel `compose up` would choose the old mutable `:local` tags. Prefer the updated start script. To inspect the deployed services:

```bash
cd ~/portfolio-demo
export DEMO_PUBLIC_ORIGIN=https://portfolio-demo.tail16175c.ts.net
IMAGES=$(python3.12 -c 'import json,pathlib; print(json.loads((pathlib.Path.home()/"demo-deploy/current.json").read_text())["images"])')
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml -f infra/public/compose.funnel.yaml -f "$IMAGES" ps -a
```

## Market 409 fix

`DEMO_STOCK` is an immutable SQL registry identity once registered. Previously bootstrap refreshed its inventory CSV, but ingestion continued using the old registered pin while smoke requested the new CSV dates. The snapshot correctly rejected the missing observations.

Bootstrap now also publishes `DEMO_STOCK_<checksum-prefix>` for every immutable artifact, retaining earlier keys/files. The smoke test captures one spec, dates and matching versioned ID before enqueueing ingestion. It never overwrites historical registry pins or loosens snapshot quality/freshness rules.
