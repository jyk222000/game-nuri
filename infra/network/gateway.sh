#!/usr/bin/env bash
# 게이트웨이 VM(proxy / monitoring) 네트워크 설정 — Rocky Linux 10
#
# 현재 17대는 이미 설정돼 있다. 이 스크립트는 VM을 새로 만들거나 다시 구성할 때의 기준이다.
# 실행 전 VirtualBox 스냅샷을 찍고, 팀장 확인 후에 실행한다.
#
# 사용법: sudo ./gateway.sh pc1   (proxy)
#         sudo ./gateway.sh pc2   (monitoring)
#
# 어댑터: enp0s3 = 브리지(공유기 192.168.0.0/24), enp0s8 = VirtualBox 내부 네트워크(pc1-net / pc2-net)
set -euo pipefail

case "${1:-}" in
  pc1) WAN_IP=192.168.0.222; LAN_IP=10.0.1.1; MY_NET=10.0.1.0/24; OTHER_NET=10.0.2.0/24; OTHER_GW=192.168.0.223 ;;
  pc2) WAN_IP=192.168.0.223; LAN_IP=10.0.2.1; MY_NET=10.0.2.0/24; OTHER_NET=10.0.1.0/24; OTHER_GW=192.168.0.222 ;;
  *) echo "사용법: $0 pc1|pc2" >&2; exit 1 ;;
esac
WAN_IF=enp0s3
LAN_IF=enp0s8
ROUTER=192.168.0.1
DNS="${DNS:-8.8.8.8 1.1.1.1}"

# 1) 주소 · 경로 · DNS (DNS는 바깥쪽 어댑터에만)
nmcli con mod "$WAN_IF" ipv4.method manual ipv4.addresses "$WAN_IP/24" ipv4.gateway "$ROUTER" \
  ipv4.dns "$DNS" ipv4.routes "$OTHER_NET $OTHER_GW" ipv6.method disabled
nmcli con mod "$LAN_IF" ipv4.method manual ipv4.addresses "$LAN_IP/24" ipv4.gateway "" \
  ipv4.dns "" ipv6.method disabled
nmcli con up "$WAN_IF"
nmcli con up "$LAN_IF"

# 2) 포워딩
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-ip-forward.conf
sysctl --system >/dev/null

# 3) 방화벽: firewalld 대신 iptables-nft-services
systemctl disable --now firewalld 2>/dev/null || true
systemctl mask firewalld
dnf install -y iptables-nft-services

iptables -C FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null ||
  iptables -I FORWARD 1 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
iptables -C FORWARD -s "$MY_NET" -i "$LAN_IF" -o "$WAN_IF" -j ACCEPT 2>/dev/null ||
  iptables -A FORWARD -s "$MY_NET" -i "$LAN_IF" -o "$WAN_IF" -j ACCEPT
iptables -C FORWARD -s "$OTHER_NET" -d "$MY_NET" -i "$WAN_IF" -o "$LAN_IF" -j ACCEPT 2>/dev/null ||
  iptables -A FORWARD -s "$OTHER_NET" -d "$MY_NET" -i "$WAN_IF" -o "$LAN_IF" -j ACCEPT
# 상대 PC 내부망으로 가는 패킷은 NAT 하지 않는다 (출발지 IP 유지)
iptables -t nat -C POSTROUTING -s "$MY_NET" ! -d "$OTHER_NET" -o "$WAN_IF" -j MASQUERADE 2>/dev/null ||
  iptables -t nat -A POSTROUTING -s "$MY_NET" ! -d "$OTHER_NET" -o "$WAN_IF" -j MASQUERADE

iptables-save > /etc/sysconfig/iptables
systemctl enable --now iptables

# 4) 확인
ip -br a
ip route
iptables -S FORWARD
iptables -t nat -S POSTROUTING
systemctl is-enabled iptables
