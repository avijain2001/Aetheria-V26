# Tailscale access

## Private Aetheria access
Run Aetheria on port 8000 and publish it privately to your tailnet with Tailscale Serve:

```bash
tailscale serve 8000
tailscale serve status
```

## Public beta / personal use
Tailscale Funnel can expose the same local service to the public internet:

```bash
tailscale funnel --bg 8000
tailscale funnel status
```

Tailscale Personal is free indefinitely for personal/non-commercial use. For a public commercial Aetheria service, use the Cloudflare Tunnel path in `deploy/oci/` and keep Tailscale Serve for private administration.
