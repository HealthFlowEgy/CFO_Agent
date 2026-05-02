# CFO Agent Deployment Guide

This guide explains how to deploy the CFO Agent to a fresh Ubuntu server (e.g., a DigitalOcean Droplet).

## Prerequisites

- A fresh Ubuntu 24.04 (or 22.04) server with root or sudo access.
- At least 2 vCPUs and 4GB RAM recommended (e.g., DigitalOcean `s-2vcpu-4gb`).
- An Anthropic API Key.

## One-Shot Deployment

We provide a bootstrap script that installs Docker, clones the repository, configures Nginx as a reverse proxy, and sets up a systemd service to ensure the app starts on boot.

SSH into your server and run:

```bash
git clone https://github.com/HealthFlowEgy/CFO_Agent.git /opt/CFO_Agent
cd /opt/CFO_Agent
sudo ./scripts/deploy.sh
```

### Configuration

After the script finishes, you must add your Anthropic API Key:

1. Open the environment file:
   ```bash
   nano /opt/CFO_Agent/.env
   ```
2. Set your key:
   ```env
   ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Restart the API container to pick up the new key:
   ```bash
   cd /opt/CFO_Agent
   make restart
   ```

## Architecture

- **FastAPI (Backend)** runs on `127.0.0.1:8000`.
- **Next.js (Frontend)** runs on `127.0.0.1:3000`.
- **PostgreSQL** runs on `127.0.0.1:5432`.
- **Nginx** listens on port `80` and routes traffic:
  - `/api/*` routes directly to FastAPI (port 8000). This bypasses Next.js to prevent Server-Sent Events (SSE) buffering issues.
  - `/` (everything else) routes to Next.js (port 3000).

The `docker-compose.override.yml` ensures containers bind only to `127.0.0.1`, preventing direct external access to the ports.

## Common Operations

A `Makefile` is included for convenience. Run these from `/opt/CFO_Agent`:

- **View all logs**: `make logs`
- **View API logs**: `make logs-api`
- **Rebuild after pulling changes**: `make rebuild`
- **Stop the app**: `make stop`
- **Restart the app**: `make restart`

## Troubleshooting

- **500 Errors on Streaming (Chat)**: Ensure Nginx is routing `/api/` directly to port 8000. If traffic goes through Next.js, SSE connections will fail. Check `/etc/nginx/sites-enabled/cfo_agent`.
- **Containers not starting on reboot**: The deployment script installs a systemd service. Check its status with `systemctl status cfo-agent.service`.
