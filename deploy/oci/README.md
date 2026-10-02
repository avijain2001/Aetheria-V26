# OCI deployment

1. Copy Aetheria to `/opt/aetheria`.
2. Install Python 3 and Tailscale.
3. Copy `aetheria.service` to `/etc/systemd/system/`.
4. Run `sudo systemctl daemon-reload && sudo systemctl enable --now aetheria`.
5. Verify `curl http://127.0.0.1:8000/api/ready`.
6. For tailnet-only access: `tailscale serve 8000`.
7. For public access: `tailscale funnel --bg 8000`.
