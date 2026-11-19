#!/usr/bin/env bash
# 내부 VM 고정 IP 설정. 사용: sudo bash internal-vm.sh <호스트이름> <IP/24> <게이트웨이>
# 예: sudo bash internal-vm.sh kafka1 10.0.1.31/24 10.0.1.1
set -euo pipefail
NAME=$1; ADDR=$2; GW=$3; IF=${IF:-enp0s3}
hostnamectl set-hostname "$NAME"
nmcli con mod "$IF" ipv4.method manual ipv4.addresses "$ADDR" ipv4.gateway "$GW" \
  ipv4.dns "8.8.8.8 1.1.1.1" ipv4.ignore-auto-dns yes
nmcli con up "$IF"
ping -c 2 "$GW" && ping -c 2 8.8.8.8 && getent hosts rockylinux.org
