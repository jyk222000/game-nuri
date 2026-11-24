#!/bin/bash
# Alloy 설치/설정 (겜누리). 여러 번 실행해도 안전. 사용:
#   EXTRA_GROUPS="mysql" FILES="mariadb-error=/var/log/mariadb/mariadb.log" bash alloy-setup.sh
set -eu
VER=1.19.2
RPM="alloy-$VER-1.amd64.rpm"
SHA=daac715d840ce8c1074c00ce0b82ed9367d5647d4daef4d2a836f154328bfb30
LOKI=http://10.0.2.1:3100
HOST=$(hostname -s)
IP=$(ip -4 -o addr show | awk '{print $4}' | cut -d/ -f1 | grep '^10\.0\.' | head -1 || true)
FILES=${FILES:-}
EXTRA_GROUPS=${EXTRA_GROUPS:-}
DRY=${DRY:-0}

mkcfg() {
cat <<EOF
logging {
  level = "warn"
}

loki.relabel "journal" {
  forward_to = []
  rule {
    source_labels = ["__journal__systemd_unit"]
    target_label  = "service"
  }
  rule {
    source_labels = ["__journal__hostname"]
    target_label  = "host"
  }
  rule {
    source_labels = ["__journal_priority_keyword"]
    target_label  = "level"
  }
}

loki.source.journal "main" {
  max_age       = "6h"
  relabel_rules = loki.relabel.journal.rules
  labels        = { job = "journal" }
  forward_to    = [loki.write.default.receiver]
}

loki.write "default" {
  endpoint {
    url = "$LOKI/loki/api/v1/push"
  }
}
EOF
i=0
for f in $FILES; do
  i=$((i+1)); svc=${f%%=*}; path=${f#*=}
cat <<EOF

local.file_match "f$i" {
  path_targets = [{
    "__path__" = "$path",
    "host"     = "$HOST",
    "service"  = "$svc",
    "job"      = "file",
  }]
}

loki.source.file "f$i" {
  targets    = local.file_match.f$i.targets
  forward_to = [loki.write.default.receiver]
}
EOF
done
}

if [ "$DRY" = 1 ]; then mkcfg; exit 0; fi

echo "== 1. 사전 확인 ($HOST, $IP)"
[ -n "$IP" ] || { echo "중단: 10.0.x.x 주소를 못 찾음"; exit 1; }
curl -fs --max-time 5 $LOKI/ready | grep -q ready || { echo "중단: Loki($LOKI)에 접속 안 됨"; exit 1; }
read -r AVAIL SIZE < <(df --output=avail,size -B1 / | tail -1)
if ! rpm -q alloy >/dev/null 2>&1; then
  LEFT=$(( (AVAIL - 720*1024*1024) * 100 / SIZE ))
  echo "설치 후 / 여유 예상: ${LEFT}%"
  [ "$LEFT" -ge 17 ] || { echo "중단: 설치 후 여유가 17% 미만(경보선 15%)"; exit 1; }
  echo "== 2. 내려받기·검증·설치"
  mkdir -p ~/alloy-install && cd ~/alloy-install
  curl -fsSLO https://github.com/grafana/alloy/releases/download/v$VER/$RPM
  echo "$SHA  $RPM" | sha256sum -c -
  sudo rpm -ivh $RPM | tail -2
  cd ~ && rm -rf ~/alloy-install
else
  echo "== 2. 이미 설치됨: $(rpm -q alloy)"
fi
echo "== 3. 권한·설정"
sudo usermod -aG systemd-journal alloy
for g in $EXTRA_GROUPS; do sudo usermod -aG "$g" alloy; done
id alloy
mkcfg | sudo tee /etc/alloy/config.alloy >/dev/null
sudo sed -i "s|^CUSTOM_ARGS=.*|CUSTOM_ARGS=\"--server.http.listen-addr=$IP:12345\"|" /etc/sysconfig/alloy
sudo mkdir -p /etc/systemd/system/alloy.service.d
printf '[Service]\nEnvironment=GOMEMLIMIT=150MiB\nMemoryMax=350M\n' | sudo tee /etc/systemd/system/alloy.service.d/override.conf >/dev/null
sudo -u alloy /usr/bin/alloy validate /etc/alloy/config.alloy && echo "설정 검사 OK"
echo "== 4. 시작·확인"
sudo systemctl daemon-reload && sudo systemctl enable alloy >/dev/null 2>&1 && sudo systemctl restart alloy
sleep 30
systemctl is-active alloy
systemctl status alloy --no-pager | grep Memory || true
curl -s -G $LOKI/loki/api/v1/label/host/values | head -c 300; echo
df -h / | tail -1
