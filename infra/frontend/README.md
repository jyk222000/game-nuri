# frontend — Frontend 1·2 배포 (nginx + 빌드 결과)

비밀번호·키는 쓰지 않는다. 화면 코드와 nginx 설정 파일은 `frontend/` 폴더(한예찬)에 있고,
이 문서는 **VM에 설치하고 배포하는 순서와 겪은 문제**만 적는다.

## 구성
```
사용자 → Proxy(HAProxy, gamenuri.store) → frontend1·2 (nginx :80) ─ /api ─▶ backend1·2 (:8000)
```
| VM | IP | nginx 설정 (레포) | `/api` 전달 대상 |
|---|---|---|---|
| frontend1 | 10.0.1.101 | `frontend/nginx/fe1.conf` | `backend1:8000` |
| frontend2 | 10.0.1.102 | `frontend/nginx/fe2.conf` | `backend2:8000` |

- nginx는 빌드 결과(정적 파일)를 `/var/www/game-nuri`에서 서빙하고, `/api/`만 짝 Backend로 전달한다.
- Frontend는 DB에 붙지 않는다. 항상 `/api`(짝 Backend)를 거친다.
- 호스트 이름(`backend1` 등)은 `/etc/hosts`(17대에 들어 있음)로 푼다. 확인: `getent hosts backend1`.

## API 모드 (빌드할 때 정한다)
`VITE_API_MODE` 값은 **빌드 때 파일 안에 굳어진다**(서버에서 바꿀 수 없음). 바꾸려면 다시 빌드해 올린다.
| 값 | 동작 | 언제 |
|---|---|---|
| `mock` (기본) | 전부 브라우저 안의 목 데이터 | Backend 없이 개발 |
| `hybrid` | Backend에 구현된 공개 조회 API(`frontend/src/api/client.js`의 `REAL_READY`)만 실서버, 실패하면 목 | 지금(구글 로그인 전) |
| `real` | 전부 실서버, 로그인도 실제 | 모든 API가 구현·적재된 뒤 |

hybrid에서 **실제 값**: 게임 목록·상세·가격·이력·최저가·할인·구매 타이밍·사양·동접자.
**목 값**: 로그인, 마이페이지, 목표가 알림, 실시간 검색어, 리뷰 요약(Backend에 API 없음).

## 설치·배포 순서 (frontend1 기준, frontend2는 `fe2.conf`로 같은 순서)
PC에서 빌드(Node.js LTS 필요):
```powershell
cd frontend
npm ci
$env:VITE_API_MODE="hybrid"; npm run build        # 결과: frontend/dist
scp -r dist admina@frontend1:~/dist
scp nginx/fe1.conf admina@frontend1:~/fe1.conf
```
VM에서:
```bash
hostname                                           # 대상 VM인지 먼저 확인
sudo dnf install -y nginx
getent hosts backend1                              # 이름이 풀리는지

sudo mkdir -p /var/www/game-nuri
sudo cp -r ~/dist/. /var/www/game-nuri/            # mv 말고 cp (SELinux 레이블 때문)
sudo cp ~/fe1.conf /etc/nginx/conf.d/game-nuri.conf
sudo restorecon -Rv /var/www /etc/nginx
sudo setsebool -P httpd_can_network_connect 1      # nginx가 Backend로 프록시하려면 필요
```
**기본 서버 블록 끄기** (아래 '겪은 문제' 1번): `/etc/nginx/nginx.conf`의 첫 `server { ... }`를 주석 처리한다.
```bash
sudo cp -p /etc/nginx/nginx.conf /etc/nginx/nginx.conf.orig
sudo awk '
  !done && !inblk && /^[[:space:]]*server[[:space:]]*\{/ { inblk=1; depth=0 }
  inblk { n=gsub(/\{/,"{"); m=gsub(/\}/,"}"); depth+=n-m; print "#" $0; if (depth<=0) { inblk=0; done=1 } ; next }
  { print }
' /etc/nginx/nginx.conf.orig | sudo tee /etc/nginx/nginx.conf >/dev/null
sudo nginx -t                                      # successful 이어야 한다
sudo systemctl enable --now nginx
```
되돌리기: `sudo cp -p /etc/nginx/nginx.conf.orig /etc/nginx/nginx.conf && sudo systemctl reload nginx`

새 빌드로 갱신할 때는 `/var/www/game-nuri/`의 파일만 교체하고 `restorecon`을 다시 한다(nginx 재시작은 필요 없음).
기존 파일을 지우는 `rm`은 대상(`/var/www/game-nuri/assets` 등)을 확인한 뒤 한다.

## 확인
```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost/      # 200 (index.html)
curl -s localhost/api/health                              # {"status":..., "server":"backend1", ...}
curl -s "localhost/api/games?size=2"                      # 게임 2건, total 1000
```
- `/api/health`의 `server` 값이 짝 Backend 이름(frontend1 → backend1)이어야 한다.
- `status: degraded`는 ES 로그인이 아직 연결되지 않아 `es: down`인 경우다(정상 범위).
- 브라우저: `https://gamenuri.store`(Proxy 경유). F12 → Network에서 `/api/...`가 200인지 본다.

## 겪은 문제
| 문제 | 원인 | 해결 |
|---|---|---|
| `nginx: command not found`, `/etc/nginx/conf.d` 없음 | nginx가 설치돼 있지 않았다 | `dnf install nginx` |
| nginx를 켜도 `/api`가 우리 설정으로 안 가고 기본 페이지가 나올 수 있음 | Rocky의 `nginx.conf`에 80포트 기본 `server`가 있고, 우리 설정(`conf.d`)보다 먼저 정의돼 기본 서버가 된다 (`nginx -T \| grep listen`에서 `listen 80`이 두 번 나옴) | `nginx.conf`의 기본 `server` 블록을 주석 처리 (위 순서) |
| `restorecon: open(/var/www) failed` | `/var/www`가 아직 없었다 | `mkdir -p` 후 `cp`, `restorecon` |

### 예상되는 문제 (이번에는 겪지 않음, Backend 배포에서 겪은 SELinux 사례로 미리 적음)
| 증상 | 예상 원인 | 해결 |
|---|---|---|
| `/api`가 502 | SELinux가 nginx의 Backend 연결을 막음 | `setsebool -P httpd_can_network_connect 1`, `sudo ausearch -m avc -ts recent`로 확인 |
| 올린 파일을 못 읽음(403) | 홈에서 `mv`한 파일은 `user_home_t` 레이블 | `cp` 사용 + `restorecon -Rv /var/www` |

## 확인 기록
| 날짜 | VM | 내용 |
|---|---|---|
| 2026-11-24 | frontend1 | nginx 1.26.3 설치, hybrid 빌드 배포. `/` 200, `/api/health`(server=backend1, db ok·valkey ok·es down), `/api/games`(total 1000). `gamenuri.store`에서 메인·상세 화면이 실제 데이터로 표시됨 |
| – | frontend2 | **미확인** (아직 같은 절차를 하지 않음) |

## 남은 일
- [ ] frontend2 배포 (`fe2.conf` → `backend2:8000`, backend2 배포 후)
- [ ] 리뷰 요약 칸: hybrid에서는 목이 실제 게임 ID를 못 찾아 "게임을 찾을 수 없습니다"로 보인다 → 빈 상태 표시로 바꾸기 (frontend, 한예찬)
- [ ] 실시간 검색어·리뷰 요약 API가 Backend에 생기면 `REAL_READY`에 추가 (frontend)
- [ ] 로그인(구글 OAuth)이 붙으면 `real` 모드로 다시 빌드
