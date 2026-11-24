#!/bin/bash
# DB exporter 설치 (겜누리). 여러 번 실행해도 안전. 사용:
#   bash exporter-setup.sh mysql   # mariadb-pr, mariadb-re
#   bash exporter-setup.sh mongo   # mongodb-pr, mongo-se1, mongo-se2
# 비밀번호는 화면에 입력만 하고, 서버 파일(권한 600)에만 저장된다.
set -eu
KIND=${1:-}
case "$KIND" in
  mysql)
    NAME=mysqld_exporter; VER=0.21.0; PORT=9104
    TGZ="mysqld_exporter-$VER.linux-amd64.tar.gz"
    URL="https://github.com/prometheus/mysqld_exporter/releases/download/v$VER/$TGZ"
    SHA=dc38d4173ab07d1e2ec8699a3957d29d31c0b9619822cc3a451771c468f704c7
    ;;
  mongo)
    NAME=mongodb_exporter; VER=0.53.0; PORT=9216
    TGZ="mongodb_exporter-$VER.linux-amd64.tar.gz"
    URL="https://github.com/percona/mongodb_exporter/releases/download/v$VER/$TGZ"
    SHA=7477ce24c607b1b0e7fcb10b49a3e437cb80004dc42195041a0da805339232e3
    ;;
  *) echo "사용법: bash exporter-setup.sh mysql|mongo"; exit 1 ;;
esac
SVC_USER=dbexporter
MON=10.0.2.1
HOST=$(hostname -s)
IP=$(ip -4 -o addr show | awk '{print $4}' | cut -d/ -f1 | grep '^10\.0\.' | head -1 || true)
[ -n "$IP" ] || { echo "중단: 10.0.x.x 주소를 못 찾음"; exit 1; }
echo "== 0. 대상: $HOST ($IP) / $NAME $VER / 포트 $PORT"

echo "== 1. 전용 사용자·바이너리"
id $SVC_USER >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /sbin/nologin $SVC_USER
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT
( cd "$D" && curl -fsSLO "$URL" && echo "$SHA  $TGZ" | sha256sum -c - && tar xzf "$TGZ" )
sudo install -m 755 -o root -g root "$D"/*/$NAME /usr/local/bin/$NAME
/usr/local/bin/$NAME --version 2>&1 | head -1 || true

echo "== 2. 비밀번호 입력 (exporter 계정의 비밀번호. 화면에 안 보이는 것이 정상)"
read -rsp "exporter 비밀번호: " PW; echo
[ -n "$PW" ] || { echo "중단: 비밀번호가 비어 있음"; exit 1; }

if [ "$KIND" = mysql ]; then
  SOCK=$(my_print_defaults --mysqld 2>/dev/null | sed -n 's/^--socket=//p' | tail -1 || true)
  [ -n "$SOCK" ] || SOCK=$(ss -xlH 2>/dev/null | awk '{print $5}' | grep -E 'mysql(d)?\.sock$' | head -1 || true)
  [ -n "$SOCK" ] || SOCK=/var/lib/mysql/mysql.sock
  [ -S "$SOCK" ] || { echo "중단: MariaDB 소켓($SOCK)을 못 찾음"; exit 1; }
  echo "   소켓: $SOCK"
  CNF=/etc/mysqld_exporter.cnf
  sudo install -m 600 -o $SVC_USER -g $SVC_USER /dev/null $CNF
  PWQ=${PW//\\/\\\\}; PWQ=${PWQ//\"/\\\"}
  printf '[client]\nuser=exporter\npassword="%s"\nsocket=%s\n' "$PWQ" "$SOCK" | sudo tee $CNF >/dev/null
  unset PWQ
  EXEC="/usr/local/bin/$NAME --config.my-cnf=$CNF --web.listen-address=$IP:$PORT"
  ENVLINE=""
else
  ENC=$(PW="$PW" python3 -c 'import os,urllib.parse as u; print(u.quote(os.environ["PW"], safe=""))')
  ENVF=/etc/mongodb_exporter.env
  sudo install -m 600 -o root -g root /dev/null $ENVF
  printf 'MONGODB_URI=mongodb://exporter:%s@127.0.0.1:27017/admin?authSource=admin\n' "$ENC" | sudo tee $ENVF >/dev/null
  EXEC="/usr/local/bin/$NAME --mongodb.direct-connect --compatible-mode --collector.diagnosticdata --collector.replicasetstatus --web.listen-address=$IP:$PORT"
  ENVLINE="EnvironmentFile=$ENVF"
fi
unset PW ENC

echo "== 3. systemd 서비스"
sudo tee /etc/systemd/system/$NAME.service >/dev/null <<EOF
[Unit]
Description=$NAME (겜누리 DB 모니터링)
After=network-online.target

[Service]
User=$SVC_USER
Group=$SVC_USER
$ENVLINE
ExecStart=$EXEC
Restart=always
RestartSec=5
MemoryMax=100M
NoNewPrivileges=true
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable $NAME >/dev/null 2>&1
sudo systemctl restart $NAME

echo "== 4. 방화벽: monitoring($MON)에서 오는 $PORT 만 허용"
if systemctl is-active --quiet firewalld; then
  RULE="rule family=\"ipv4\" source address=\"$MON\" port port=\"$PORT\" protocol=\"tcp\" accept"
  if sudo firewall-cmd --permanent --query-rich-rule="$RULE" >/dev/null 2>&1; then
    echo "   이미 있음"
  else
    sudo firewall-cmd --permanent --add-rich-rule="$RULE" >/dev/null
    sudo firewall-cmd --reload >/dev/null
    echo "   추가함"
  fi
else
  echo "   firewalld 꺼져 있음 → 건너뜀"
fi

echo "== 5. 확인"
sleep 4
systemctl is-active $NAME
if [ "$KIND" = mysql ]; then
  curl -s http://$IP:$PORT/metrics | grep -E '^mysql_up |^mysql_slave_status_(slave_io_running|slave_sql_running|seconds_behind_master)' || echo "   mysql_up 줄 없음 → journalctl -u $NAME -n 20"
else
  curl -s http://$IP:$PORT/metrics | grep -E '^mongodb_up |^mongodb_mongod_replset_my_state' || echo "   mongodb_up 줄 없음 → journalctl -u $NAME -n 20"
fi
systemctl show $NAME -p MemoryCurrent | head -1
df -h / | tail -1
