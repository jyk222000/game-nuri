# 리뷰 요약 배치(⑤) 운영 문서

`collector/collector/review_summary.py`. ES 리뷰 키워드 → AI 요약 → `refined.review_summary` → MariaDB `review_summaries`.
이 문서는 **지금 어떻게 설정돼 있고, 앞으로 무엇을 해야 하는지**를 적는다. 코드 동작은 파일 맨 위 설명이 기준이다.

## 1. 하는 일
1. `analysis/game_list/games_1000.csv`의 게임 1,000개를 순서대로 처리한다.
2. ES `reviews`(한국어 Steam 리뷰)에서 게임마다 장점·단점 키워드와 긍정률을 뽑는다.
   - `review.nouns`에 `significant_terms`, 긍정 쪽은 부정 리뷰를, 부정 쪽은 긍정 리뷰를 비교 대상으로 둔다. 점수는 `chi_square`.
   - 장점은 5개 이상, 단점은 3개 이상의 리뷰에 나와야 한다. 한쪽 최대 8개.
   - 리뷰가 30건 미만이면 건너뛴다.
3. 가격·평가·감정 단어, 욕설·민감어, 게임 이름 조각은 키워드에서 뺀다(코드의 `STOPWORDS`, `SENSITIVE_WORDS`, `PROFANITY`).
4. **키워드·긍정률·게임 이름만** Gemini에 보내 한두 문장 요약(JSON)을 받는다. 리뷰 원문은 보내지 않는다.
5. 결과를 `refined.review_summary`로 보낸다. 같은 `game_id`는 덮어쓴다(upsert).
   - AI 성공: `generated_by=ai` + 요약 문장
   - AI 안 씀·실패: `generated_by=fallback` + 키워드만(요약 문장 비움). 화면은 키워드만 보여 준다.
   - 요약에 욕설이 섞이면 버리고 fallback으로 보낸다.

## 2. 2단계로 나눠 돌리는 이유
Gemini 무료 등급(`gemini-3.5-flash-lite`)은 분당 15회, **하루 500회**이고 프로젝트 하나를 사양 판정(⑥)과 같이 쓴다.
실패한 호출(503·시간 초과)도 하루 한도에 들어간다. 1,000개를 한 번에 AI로 돌릴 수 없다.

| 단계 | 명령 | 하는 일 |
|---|---|---|
| 1단계 | `--no-ai` | AI 없이 키워드만 1,000개 전부 저장(fallback). **완료.** |
| 2단계 | `--ai-only --max-ai-calls N --skip K` | 키워드가 이미 있는 게임에 요약 문장을 채운다. 하루에 조금씩. **진행 중.** |

주의: `--no-ai`는 같은 게임을 fallback으로 **덮어써서 AI 요약이 지워진다.** 2단계를 시작한 뒤에는 쓰지 않는다.

## 3. 안전장치 (옵션)
| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--ai-only` | 꺼짐 | AI가 실패한 게임은 보내지 않는다(기존 값을 fallback으로 덮지 않으려고) |
| `--max-ai-calls N` | 제한 없음 | AI 호출(재시도 포함) 상한. 닿으면 멈추고 `--skip` 값을 로그에 남긴다 |
| `--skip K` | 0 | 앞의 K개 게임을 건너뛴다(이어서 하기) |
| `--ai-interval` | 6초 | 호출 간격. 분당 10회 이하 |
| `--failure-pause` | 60초 | 연속 3번 실패하면 쉰다. 계속 실패하면 120→240→…최대 600초 |
| `--stop-after-failures` | 12 | 연속 12번 실패하면 멈춘다 |
| `--game-ids a,b` | – | 지정한 게임만(실패한 게임 재시도용) |
| `--dry-run` | – | Kafka로 보내지 않고 `samples/`에 저장 |

실패 대부분은 Google 쪽 과부하(503)다. 지금까지 성공률은 약 50~57%다.

## 4. 실행 방법 (수집 서버 proxy, 사용자가 직접)
서버 설정(`GEMINI_API_KEY`, `AI_MODEL` 등)은 `/etc/game-nuri/collector.env`에 있다. 값은 커밋하지 않는다.
```bash
sudo -u collector bash -c 'set -a; . /etc/game-nuri/collector.env; set +a; cd /opt/game-nuri/repo/collector && nohup /opt/game-nuri/repo/.venv/bin/python -m collector.review_summary --ai-only --max-ai-calls 290 --skip <K> > /tmp/review_summary_ai<번호>.log 2>&1 &'
tail -f /tmp/review_summary_ai<번호>.log        # 진행 보기
pgrep -u collector -f collector.review_summary   # 돌고 있는지
tail -4 /tmp/review_summary_ai<번호>.log         # 끝난 뒤: "이어서 하려면 --skip K" 확인
```
- `nohup`이라 접속을 끊어도 계속 돈다.
- 타이머(systemd)로 자동화하지 않았다. `--skip` 값을 사람이 이어 줘야 하고, 한도를 사양 판정과 나눠 써야 하기 때문이다.

## 5. 지금까지 (11/25 기준)
- 1단계 완료: 1,000개 키워드 저장.
- 2단계: 11/24 밤 `--skip 23`, 호출 290회 → 11/25 03시 종료, AI 요약 **21 → 228개**. 다음 시작 위치 `--skip 236`.
- 11/25 낮 `--max-ai-calls 60`으로 추가 진행 중(결과는 로그 확인).
- 3번 연속 실패해 보내지 않은 게임이 있다(예: `111469`, `25076`, `7360`). 아래 6번에서 다시 돌린다.

## 6. 앞으로 할 일
1. **하루 호출 상한을 지킨다.** 하루 약 400회 이내, 사양 판정용으로 **100회 이상 남긴다.** 돌리기 전에 Google AI Studio의 비율 제한 화면에서 RPD(오늘 사용량)를 확인한다.
   - RPD는 태평양 자정 초기화가 아니라 최근 24시간 합계처럼 움직이는 것으로 보인다(확인 못 함). 돌리기 직전 숫자를 보고 정한다.
2. 하루 한두 번, 로그에 나온 `--skip` 값으로 이어서 돌린다. 앞쪽 게임일수록 인기 있는 게임이므로 순서를 유지한다.
3. 실패한 게임 재시도:
   ```bash
   grep "전송하지 않음" /tmp/review_summary_ai*.log | grep -o 'game_id=[0-9]*' | cut -d= -f2 | sort -u | paste -sd,
   ```
   나온 번호를 `--ai-only --game-ids <번호들>`로 다시 돌린다.
4. 발표 전 마감: 상위 약 550~680개를 11/27쯤까지 채운다. **11/29·11/30에는 돌리지 않는다**(사양 판정 시연이 한도를 써야 한다).
5. 끝까지 못 채운 게임은 키워드만 보인다. 화면에 "요약 준비 중" 안내가 필요하다(프런트 작업).
6. 확인할 것: DB 개수 `SELECT generated_by, COUNT(*) FROM review_summaries GROUP BY generated_by;`

## 7. 하지 말 것
- 2단계 중에 `--no-ai`로 전체를 다시 돌리지 않는다(AI 요약이 지워진다).
- 리뷰 원문을 AI에 보내도록 바꾸지 않는다(`CLAUDE.md` 4-9).
- API 키·`.env` 내용을 로그·문서·커밋에 쓰지 않는다.
- 같은 시간에 배치를 두 개 이상 띄우지 않는다(한도를 같이 쓴다).
