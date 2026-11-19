#!/usr/bin/env bash
# Proxy VM에서 1회 실행: 내부망 → 외부 NAT
set -euo pipefail
OUT_IF="${1:-enp0s3}"
echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-nat.conf
sudo sysctl --system
sudo iptables -t nat -A POSTROUTING -s 192.168.100.0/24 -o "$OUT_IF" -j MASQUERADE
sudo apt-get install -y iptables-persistent
