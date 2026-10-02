# Aetheria V23.1 — 24×7 deployment options

## Recommended
Run the Aetheria engine on an always-on Linux VM and use Tailscale for secure access. The application remains self-contained; no third-party LLM is required.

### Tailscale Serve (private to your tailnet)
After starting Aetheria on port 8000:

```bash
tailscale serve 8000
```

Serve is appropriate when only your devices/users in the Tailscale network need access. Tailscale documents Serve as the private alternative to Funnel.

### Tailscale Funnel (public HTTPS)
For a public URL:

```bash
tailscale funnel --bg 8000
tailscale funnel status
```

Funnel exposes the local service over HTTPS; the service host must stay online. Do not expose sensitive administration endpoints publicly.

## Always-on Windows
Use `Start_Aetheria.vbs` through Windows Task Scheduler at logon/startup. This avoids opening CMD manually, but the PC must remain powered on.

## Oracle Cloud Always Free
For a free 24×7 host, an Oracle Always Free A1 Ampere VM is a practical fit for the Python/SQLite workload when capacity is available. Oracle's current Always Free documentation provides up to 2 OCPU and 12 GB RAM for the A1 allocation in a tenancy; capacity can be constrained by region.

Suggested stack:

```text
Oracle Linux/Ubuntu VM
  ├─ Aetheria Python service (systemd)
  ├─ SQLite/WAL + retained world memory
  ├─ Tailscale Serve or Funnel
  └─ optional Cloudflare DNS/edge
```

Cloudflare Workers Free should be kept as a thin edge/API layer, not used as the 184+ feed crawler; its current Free plan has request/CPU/subrequest limits.

## Service
Use `deploy/oci/aetheria.service` with the project directory copied to `/opt/aetheria`.


## Public 24×7 recommendation
For a private/personal deployment, Tailscale Personal is free indefinitely and supports up to six users; use Tailscale Serve for private tailnet access. Tailscale Personal is intended for non-commercial use.

For a public Aetheria service, use an always-on Linux VM plus `cloudflared` and keep Tailscale Serve for private administration. Cloudflare Tunnel is available on all Cloudflare plans and uses an outbound-only tunnel, avoiding an exposed origin port.

Recommended production shape:
```text
Oracle Always Free A1 / Linux VM
    ├─ Aetheria engine + SQLite/WAL
    ├─ systemd → automatic restart / boot
    ├─ cloudflared → public HTTPS
    └─ Tailscale Serve → private admin access
```

Do not use Tailscale Funnel as the commercial production front door; its free Personal plan is for non-commercial use, while Funnel itself is a public-internet exposure mechanism.


## Cloudflare Tunnel production path
For a public service, create a named Cloudflare Tunnel on the always-on VM and map a hostname to `http://127.0.0.1:8000`. Keep the Aetheria origin bound to localhost. Cloudflare Tunnel is available on all plans and uses an outbound-only connection, so no inbound application port needs to be exposed on the VM.

Example operator flow (credentials and hostname are intentionally not hardcoded):
```bash
cloudflared tunnel login
cloudflared tunnel create aetheria
cloudflared tunnel route dns aetheria news.example.com
cloudflared tunnel --config /etc/cloudflared/config.yml run aetheria
```

Example `/etc/cloudflared/config.yml`:
```yaml
tunnel: <TUNNEL_UUID>
credentials-file: /etc/cloudflared/<TUNNEL_UUID>.json
ingress:
  - hostname: news.example.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

Use Tailscale Serve separately for private administration. Do not expose `/api/diagnostics`, `/api/sources`, or other operator surfaces publicly without authentication.
