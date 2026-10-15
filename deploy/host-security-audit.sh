#!/usr/bin/env bash
# Read-only Linux host security report; makes NO firewall/SSH/cloud changes.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Host audit requires a Linux server; no changes made."
  exit 2
fi

echo "== yanhaoo host pre-publication security audit =="
date -u '+Audit time (UTC): %Y-%m-%dT%H:%M:%SZ'
echo "Mode: READ ONLY. No firewall or SSH configuration changes."
echo

echo "[1] Public listeners (review IP bindings before enabling DNS)"
if command -v ss >/dev/null 2>&1; then
  ss -H -ltn | awk '{ print $4 }' | sort -u
else
  echo "UNVERIFIED: ss utility unavailable"
fi
echo

echo "[2] UFW host firewall"
if command -v ufw >/dev/null 2>&1; then
  ufw status verbose 2>&1 || echo "UNVERIFIED: elevated access may be required"
else
  echo "UNVERIFIED: ufw not installed (check nftables/firewalld)"
fi
echo

echo "[3] SSH daemon security policy"
if command -v sshd >/dev/null 2>&1; then
  # Without root, sshd -T may not show effective Match/user-specific settings.
  if settings="$(sshd -T 2>/dev/null)"; then
    printf '%s\n' "$settings" | grep -E '^(port|permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|allowusers) ' || true
  else
    echo "UNVERIFIED: run sudo sshd -T separately to check effective settings"
  fi
else
  echo "UNVERIFIED: sshd not on PATH (some systems place it in /usr/sbin)"
fi
echo

echo "[4] Pending security updates (read-only)"
if command -v apt-get >/dev/null 2>&1; then
  if command -v apt >/dev/null 2>&1; then
    apt list --upgradable 2>/dev/null | sed -n '1,20p'
  fi
  systemctl is-enabled unattended-upgrades 2>/dev/null || true
  systemctl is-active unattended-upgrades 2>/dev/null || true
else
  echo "UNVERIFIED: apt unavailable"
fi
echo

echo "[5] Docker published ports / running services"
if command -v docker >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}' 2>&1 || echo "UNVERIFIED: Docker permission required"
else
  echo "UNVERIFIED: Docker unavailable"
fi
echo "IMPORTANT: Docker-published ports may bypass UFW rules; check both container bindings AND Tencent Cloud security group."
echo

echo "[6] Disk and memory capacity"
df -h / | tail -n 1
free -h | sed -n '1,2p' || true
echo

echo "Read-only review finished. Do NOT expose 80/443 before ICP readiness and public access verification."
