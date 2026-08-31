#!/usr/bin/env bash
# Run locally on the Pi as root (or with sudo). Usage: setup_ssh.sh SSH_PUBLIC_KEY [HOSTNAME]
set -euo pipefail
KEY=${1:?"usage: $0 SSH_PUBLIC_KEY [HOSTNAME]"}
HOSTNAME=${2:-network-sentinel-pi}
USER=sentinel
apt-get update
apt-get install -y openssh-server avahi-daemon
id "$USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$USER"
install -d -m 700 -o "$USER" -g "$USER" "/home/$USER/.ssh"
printf '%s\n' "$KEY" > "/home/$USER/.ssh/authorized_keys"
chown "$USER:$USER" "/home/$USER/.ssh/authorized_keys"
chmod 600 "/home/$USER/.ssh/authorized_keys"
hostnamectl set-hostname "$HOSTNAME"
install -d -m 755 /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/network-sentinel.conf <<'EOF'
# Managed by Network Sentinel setup
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
AllowUsers sentinel
EOF
sshd -t
systemctl enable --now ssh avahi-daemon
systemctl restart ssh
printf 'SSH: ssh sentinel@%s.local\n' "$HOSTNAME"
