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
| `real` (**기본**, 값을 안 주면 이 모드) | 전부 실서버 `/api`. 구글 로그인도 실제 로그인으로 연결 | **서버에 올리는 빌드는 항상 이 모드** |
| `mock` | 전부 브라우저 안의 목 데이터 | Backend 없이 화면만 개발할 때 (`VITE_API_MODE=mock`으로 명시) |

(`hybrid` 모드는 frontend #89에서 없어졌다. 목 분석 데이터 파일도 지워졌다.)

`real`에서는 Backend에 없는 API를 부르면 목으로 대신하지 않고 **그대로 오류**가 난다. 2026-11-24 기준
Backend에 아직 없는 것: 리뷰·리뷰 요약(`/api/games/{id}/reviews*`),
사양 비교(`/spec-check`), 실시간·최근 검색어(`/api/search/*`). 이 화면들이 오류 대신 빈 상태로
보이는지는 **미확인**이다(frontend 담당).

## 설치·배포 순서 (frontend1 기준, frontend2는 `fe2.conf`로 같은 순서)
PC에서 빌드(Node.js LTS 필요):
```powershell
cd frontend
npm ci
npm run build                                     # 결과: frontend/dist (기본이 real. VITE_API_MODE를 주지 않는다)
scp -r dist admina@frontend1:~/dist
scp nginx/fe1.conf admina@frontend1:~/fe1.conf
```
VM에서:
```bash
hostname                                           # 대상 VM인지 먼저 확인
sudo dnf install -y nginx
getent hosts backend1                              # 이름이 풀리는지

sudo mkdir -p /var/www/game-nuri
# 새 빌드로 갱신할 때만: 옛 파일이 남지 않게 먼저 비운다 (아래 '새 빌드로 갱신' 참고)
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

### 새 빌드로 갱신할 때 (옛 파일 비우기)
빌드마다 `assets/` 파일 이름(해시)이 바뀌고, 예전 빌드에는 `analysis-data/`도 있었다. `cp`만 하면 옛 파일이
남아 용량만 차지하고 헷갈린다. **지우기 전에 목록을 보고**, 대상이 맞는지 확인한 뒤 실행한다.
```bash
hostname                                           # 대상 VM인지 확인
ls /var/www/game-nuri                              # index.html, assets, (analysis-data) 등
sudo rm -r /var/www/game-nuri/assets /var/www/game-nuri/analysis-data   # 없다는 메시지는 무시
sudo cp -r ~/dist/. /var/www/game-nuri/
sudo restorecon -Rv /var/www
```
- 이 `rm -r`은 위 두 폴더만 지운다. `/var/www/game-nuri` 전체를 지우지 않는다(`index.html`이 잠깐 없어지면 사이트가 404).
- 갱신 후 nginx 재시작은 필요 없다. 브라우저는 강력 새로고침(Ctrl+F5)으로 확인한다.

## 확인
```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost/      # 200 (index.html)
curl -s localhost/api/health                              # {"status":"ok", "server":"backend1", ...}
curl -s "localhost/api/games?size=2"                      # 게임 2건, total 1000
```
- `/api/health`의 `server` 값이 짝 Backend 이름(frontend1 → backend1)이어야 한다.
- `status: ok`, `es: ok`가 정상이다(ES 로그인 적용 후, 2026-11-24 backend1에서 확인).
  `degraded`이면 `es`·`valkey` 중 어느 것이 `down`인지 본다.
- 브라우저: `https://gamenuri.store`(Proxy 경유). F12 → Network에서 `/api/...`가 200인지 본다.

## 겪은 문제
| 문제 | 원인 | 해결 |
|---|---|---|
| `nginx: command not found`, `/etc/nginx/conf.d` 없음 | nginx가 설치돼 있지 않았다 | `dnf install nginx` |
| nginx를 켜도 `/api`가 우리 설정으로 안 가고 기본 페이지가 나올 수 있음 | Rocky의 `nginx.conf`에 80포트 기본 `server`가 있고, 우리 설정(`conf.d`)보다 먼저 정의돼 기본 서버가 된다 (`nginx -T \| grep listen`에서 `listen 80`이 두 번 나옴) | `nginx.conf`의 기본 `server` 블록을 주석 처리 (위 순서) |
| `restorecon: open(/var/www) failed` | `/var/www`가 아직 없었다 | `mkdir -p` 후 `cp`, `restorecon` |
| frontend2에서 `cp: cannot stat '/home/admind/fe2.conf'` | `scp`로 `dist`만 올리고 `fe2.conf`를 올리지 않았다. 이 상태에서 기본 서버 블록을 주석 처리하고 nginx를 켜면 80포트에 응답할 서버가 없다 | `fe2.conf`를 올리고 `conf.d/game-nuri.conf`로 복사한 뒤 `nginx -t`, `reload` |
| 서버 화면이 옛 버전 | 올린 `dist`가 옛 빌드였다(`assets`가 `index-DrnNiEl6.js`). `ls`로 새 파일 이름을 확인하지 않고 `cp`했다 | 새 `dist`를 `~/dist_new`로 다시 올려 파일 이름을 확인한 뒤 갱신. 폴더 중첩을 피하려고 `dist_new`처럼 새 이름을 쓴다 |

### 예상되는 문제 (이번에는 겪지 않음, Backend 배포에서 겪은 SELinux 사례로 미리 적음)
| 증상 | 예상 원인 | 해결 |
|---|---|---|
| `/api`가 502 | SELinux가 nginx의 Backend 연결을 막음 | `setsebool -P httpd_can_network_connect 1`, `sudo ausearch -m avc -ts recent`로 확인 |
| 올린 파일을 못 읽음(403) | 홈에서 `mv`한 파일은 `user_home_t` 레이블 | `cp` 사용 + `restorecon -Rv /var/www` |

## 확인 기록
| 날짜 | VM | 내용 |
|---|---|---|
| 2026-11-24 | frontend1 | nginx 1.26.3 설치, **hybrid 빌드**(당시) 배포. `/` 200, `/api/health`(server=backend1, db ok·valkey ok·es down), `/api/games`(total 1000). `gamenuri.store`에서 메인·상세 화면이 실제 데이터로 표시됨 |
| 2026-11-24 | frontend1 | **real 기본 빌드**(main 1b7d66f 기준, `assets`는 `index-DLW11KPE.css`·`index-DWheRICh.js` 2개)로 재배포. 옛 `assets`를 비운 뒤 `cp`, `restorecon`. `/` 200, `/api/health` ok(server=backend1, db·valkey·es ok), `/api/games` 응답 확인 |
| 2026-11-24 | frontend1·backend1 | 구글 로그인 확인(backend #99·#100 배포 후): `gamenuri.store`에서 로그인 → 마이페이지에 구글 계정 이메일·닉네임 표시. `AUTH_FAKE_USER=false`로 끈 상태 |
| 2026-11-26 | frontend1 | 새 빌드(main cfd324d 기준, `assets`는 `index-DIr7GOr6.css`·`index-rI9v3tce.js`)로 재배포. 상세 화면 추가 정보(개발사·연령·시리즈·Steam 리뷰 수)와 분석 탭·할인 메뉴 제거가 들어갔다. 옛 `assets`를 비운 뒤 `cp`, `restorecon`. `curl localhost/`로 새 파일 이름 확인 |
| 2026-11-26 | frontend2 | **처음 배포**. nginx 1.26.3 설치, 같은 빌드 배치, `fe2.conf`(`backend2:8000`) 적용, 기본 서버 블록 주석 처리. `/` 200, 새 파일 이름 확인, `/api/health` ok(server=backend2, db_write·db_read·valkey·es ok), `/api/games` total 1000 |
| 2026-11-26 | proxy | `gamenuri.store/api/health`를 반복 호출해 `server`가 backend1·backend2로 번갈아 나오는 것 확인(HAProxy 라운드로빈, 두 서버 모두 투입) |
| 2026-11-26 | backend1·2 | `SESSION_SECRET`이 같고, `gamenuri.store`에서 로그인 후 새로고침해도 로그인이 유지되는 것 확인 |

## 남은 일
- [x] frontend1에 real 기본 빌드 올리기 (2026-11-24)
- [x] frontend2에 real 기본 빌드 올리기 (`fe2.conf` → `backend2:8000`, 2026-11-26)
- [ ] Backend에 없는 API(로그인·리뷰·사양 비교·검색어)를 만들고, 그 전까지 해당 화면이 오류가 아닌 빈 상태로 보이게 하기 (frontend, 한예찬)
- [x] 구글 로그인이 동작하는지 확인하고 개발용 `AUTH_FAKE_USER`를 끈다 (backend1, 2026-11-24)
- [x] backend2에도 같은 `GOOGLE_*`·`SESSION_SECRET`을 넣고 `AUTH_FAKE_USER=false`인지 확인 (두 서버가 같은 `SESSION_SECRET`이어야 로그인이 서로 통한다, 2026-11-26)
- [ ] 로그인 실패·취소 때 JSON 오류가 그대로 보이는 문제 (`/login?error=...` 방식은 프론트·백엔드 합의 필요)
