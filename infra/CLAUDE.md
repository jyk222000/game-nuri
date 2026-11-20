# infra — 서버 설정

**하는 일:** VM·네트워크·HAProxy·Kafka·DB·ELK·Valkey·모니터링·백업 설정을 **파일로** 관리한다.

## 지킬 것
- 서버에서 손으로 바꾼 설정은 반드시 이 폴더에 같은 내용으로 커밋한다. "서버에만 있는 설정"을 만들지 않는다.
- 비밀번호·키는 파일에 쓰지 않는다. `*.example`로 두고 실제 값은 서버의 `.env` 또는 `/etc/game-nuri/`에.
- IP·호스트 이름의 기준은 `docs/network.md`. OS는 Rocky Linux 10이다 (패키지는 `dnf`, apt·netplan 아님).
- 현재 인프라 상태와 남은 작업은 `docs/infra-status.md`.
- 설치 전 VirtualBox 스냅샷을 찍는다. 설치 순서와 명령은 각 폴더 `README.md`에 남긴다.
- Claude는 VM에서 명령을 실행하기 전에 항상 사용자에게 확인받는다. DB·토픽 삭제는 하지 않는다.

## 폴더
| 폴더 | 내용 |
|---|---|
| `network/` | 게이트웨이(NAT·경로)·내부 VM 네트워크 스크립트 (Rocky Linux 10, nmcli) |
| `ssh/` | 팀원용 `~/.ssh/config` 예시 (점프 서버) |
| `hosts` | `/etc/hosts`에 넣을 호스트 목록 |
| `haproxy/` | Proxy 설정 |
| `kafka/` | 브로커 설정, 토픽 생성 스크립트 |
| `mariadb/`, `mongodb/`, `elk/`, `valkey/` | 설치·복제 설정 |
| `monitoring/` | Prometheus·Grafana·알림 규칙 |
| `backup/` | 백업 스크립트, crontab |
| `local/` | 각자 PC 개발용 docker-compose |
