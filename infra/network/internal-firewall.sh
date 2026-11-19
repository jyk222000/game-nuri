#!/usr/bin/env bash
# 내부 VM 15대에서 1회 실행 (1부 단계): 두 내부망(10.0.0.0/16)에서 오는 것은 허용, 그 밖은 차단
# 서비스별 포트 좁히기는 2부에서
set -euo pipefail
systemctl disable --now firewalld 2>/dev/null || true
systemctl mask firewalld
systemctl disable --now nftables 2>/dev/null || true
dnf install -y iptables-nft-services >/dev/null
iptables -F
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p icmp -j ACCEPT
iptables -A INPUT -s 10.0.0.0/16 -j ACCEPT
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT
iptables-save > /etc/sysconfig/iptables
systemctl enable --now iptables
iptables -S
