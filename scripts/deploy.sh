#!/usr/bin/env bash
set -e

echo "Starting CFO_Agent Deployment..."

# 1. Update and install prerequisites
echo "Installing prerequisites..."
apt-get update -y
apt-get install -y git curl nginx ufw

# 2. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

# 3. Setup repo
REPO_DIR="/opt/CFO_Agent"
if [ ! -d "$REPO_DIR" ]; then
    echo "Cloning repository to $REPO_DIR..."
    git clone https://github.com/HealthFlowEgy/CFO_Agent.git "$REPO_DIR"
else
    echo "Repository already exists at $REPO_DIR. Pulling latest..."
    cd "$REPO_DIR"
    git fetch origin
    git checkout main
    git pull origin main
fi

cd "$REPO_DIR"

# 4. Setup .env if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Generating new JWT_SECRET..."
    sed -i "s/JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env
    echo "PLEASE EDIT $REPO_DIR/.env to set ANTHROPIC_API_KEY and other variables."
fi

# 5. Setup Nginx
echo "Configuring Nginx..."
cp deploy/nginx/cfo_agent.nginx.conf /etc/nginx/sites-available/cfo_agent
ln -sf /etc/nginx/sites-available/cfo_agent /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# 6. Setup Systemd Service
echo "Configuring systemd service..."
cat <<EOF > /etc/systemd/system/cfo-agent.service
[Unit]
Description=CFO Agent docker-compose stack
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/CFO_Agent
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cfo-agent.service

# 7. Start the stack
echo "Starting Docker Compose stack..."
docker compose up -d --build

# 8. Setup UFW Firewall
echo "Configuring firewall..."
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo "Deployment complete!"
echo "Your app is running. Don't forget to update $REPO_DIR/.env with your Anthropic API Key!"
