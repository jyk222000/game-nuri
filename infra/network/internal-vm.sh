#!/usr/bin/env bash
# 내부 VM 네트워크 설정 — Rocky Linux 10
#
# 현재 17대는 이미 설정돼 있다. 이 스크립트는 VM을 새로 만들거나 다시 구성할 때의 기준이다.
# 실행 전 VirtualBox 스냅샷을 찍고, 팀장 확인 후에 실행한다.
#
# 사용법: sudo ./internal-vm.sh <호스트이름>     예) sudo ./internal-vm.sh kafka1
# IP는 infra/hosts 에서 찾는다. 어댑터는 enp0s3 하나(VirtualBox 내부 네트워크 pc1-net / pc2-net).
set -euo pipefail

NAME="${1:?사용법: $0 <호스트이름>}"
HOSTS_FILE="$(dirname "$0")/../hosts"
IP="$(awk -v n="$NAME" '$2==n {print $1}' "$HOSTS_FILE")"
[ -n "$IP" ] || { echo "$NAME 이(가) $HOSTS_FILE 에 없음" >&2; exit 1; }
GW="${IP%.*}.1"            # 10.0.1.x → 10.0.1.1 (proxy), 10.0.2.x → 10.0.2.1 (monitoring)
IF=enp0s3
DNS="${DNS:-8.8.8.8 1.1.1.1}"

hostnamectl set-hostname "$NAME"
nmcli con mod "$IF" ipv4.method manual ipv4.addresses "$IP/24" ipv4.gateway "$GW" \
  ipv4.dns "$DNS" ipv6.method disabled
nmcli con up "$IF"

# /etc/hosts: 127.0.0.1·::1 줄은 두고, 기존 팀 호스트 줄을 infra/hosts 내용으로 교체한다 (덧붙이지 않음)
cp /etc/hosts "/etc/hosts.bak.$(date +%Y%m%d-%H%M)"
grep -E '^(127\.|::1)' /etc/hosts > /etc/hosts.new
grep -vE '^\s*(#|$)' "$HOSTS_FILE" >> /etc/hosts.new
mv /etc/hosts.new /etc/hosts

# 확인
hostnamectl --static
ip -br a
ip route
ping -c 2 "$GW"
ping -c 2 8.8.8.8
getent hosts kafka1 mariadb-pr
