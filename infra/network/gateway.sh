#!/usr/bin/env bash
# 게이트웨이 VM(proxy=pc1, monitor=pc2)에서 1회 실행: 포워딩, 두 내부망 라우팅, 인터넷 NAT, 기본 방화벽
# 사용: sudo bash gateway.sh pc1   (proxy)   /   sudo bash gateway.sh pc2   (monitor)
# 전제: 워크북 2-1 / 2-2의 nmcli 설정(브리지 IP, 내부 IP, ipv4.routes)이 끝난 상태
set -euo pipefail
WAN=enp0s3      # 브리지 (공유기망 192.168.0.0/24)
LAN=enp0s8      # 내부 네트워크
case "${1:-}" in
  pc1) MY=10.0.1.0/24; OTHER=10.0.2.0/24; SERVICE_PORTS="80 443" ;;
  pc2) MY=10.0.2.0/24; OTHER=10.0.1.0/24; SERVICE_PORTS="3000" ;;
  *) echo "사용: $0 pc1|pc2"; exit 1 ;;
esac

echo 'net.ipv4.ip_forward = 1' > /etc/sysctl.d/99-forward.conf
sysctl --system >/dev/null

systemctl disable --now firewalld 2>/dev/null || true
systemctl mask firewalld
systemctl disable --now nftables 2>/dev/null || true
dnf install -y iptables-nft-services >/dev/null

iptables -F; iptables -t nat -F
# INPUT
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p icmp -j ACCEPT
iptables -A INPUT -p tcp -s 192.168.0.0/24 --dport 22 -j ACCEPT
iptables -A INPUT -p tcp -s 10.0.0.0/16 --dport 22 -j ACCEPT
iptables -A INPUT -s 10.0.0.0/16 -j ACCEPT            # 1부: 내부망에서 오는 것 허용 (node_exporter 등)
for p in $SERVICE_PORTS; do iptables -A INPUT -p tcp --dport "$p" -j ACCEPT; done
# FORWARD: 내 내부망 → 밖, 응답, 두 내부망 사이
iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A FORWARD -i "$LAN" -o "$WAN" -s "$MY" -j ACCEPT
iptables -A FORWARD -i "$WAN" -o "$LAN" -s "$OTHER" -d "$MY" -j ACCEPT
# NAT: 인터넷으로 나갈 때만 (상대 내부망으로 갈 때는 주소 그대로)
iptables -t nat -A POSTROUTING -s "$MY" ! -d "$OTHER" -o "$WAN" -j MASQUERADE
# 정책은 맨 마지막 (SSH 끊김 방지)
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# 저장 → 서비스 켜기 (순서 중요)
iptables-save > /etc/sysconfig/iptables
systemctl enable --now iptables
iptables -S; iptables -t nat -S
echo "gateway $1 ok"
