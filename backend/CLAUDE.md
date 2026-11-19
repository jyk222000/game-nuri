# backend — FastAPI

**하는 일:** `docs/contracts/api.md`의 API 제공, 클릭스트림을 Kafka로 발행.
**배포:** Backend 1·2 VM (같은 코드, `.env`의 `SERVER_NAME`만 be1/be2)

## 구조
```
app/
  main.py          # FastAPI 앱, 라우터 등록, /api/health
  api/             # 라우터 (games.py, auth.py, me.py, events.py) — 얇게 유지
  services/        # 비즈니스 로직 (timing.py, alerts.py ...)
  db/              # SQLAlchemy 모델·세션 (erd.sql과 일치)
  clients/         # es.py, valkey.py, kafka.py
```

## 지킬 것
- API 경로·응답 형식은 `docs/contracts/api.md`가 기준. 바꿔야 하면 contracts PR 먼저.
- **가격·게임 테이블에는 쓰지 않는다** (Kafka Connect 담당). 쓰기는 users, alerts, alert_logs만.
- 읽기는 `MARIADB_READ_HOST`(Replica), 쓰기는 `MARIADB_HOST`(Primary).
- 세션·캐시·알림 중복 키는 Valkey에. 키 규칙: `session:{id}`, `cache:prices:{game_id}`(TTL 10분), `alert_sent:{alert_id}:{price}`.
- 라우터에서 DB를 직접 다루지 말고 services를 거친다.
- 비밀번호는 bcrypt 해시. 로그에 개인정보·토큰을 남기지 않는다.

## 실행
```bash
pip install -e ../shared -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
