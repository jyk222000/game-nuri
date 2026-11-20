# collector/experiments — 수집 가능성 시험 스크립트 (NW2-83)

운영 코드가 아니라 후보 게임 15종으로 IGDB·Steam·ITAD·다나와 수집 가능 여부를 확인한 **일회성 시험 스크립트**입니다.
결과 문서는 `docs/collector-test/`에 있습니다. 린트 검사는 파일 맨 위 `# ruff: noqa`로 제외했습니다.

| 스크립트 | 하는 일 |
|---|---|
| `check_candidates.py` | 후보 15종을 IGDB·Steam·ITAD·다나와로 조회하고 원본 JSON 저장 |
| `check_gaps.py` | 위 시험에서 비어 있던 항목 보완 확인 |
| `check_steam_user.py` | Steam 개인 데이터(보유 게임·업적 등) 수집 확인 (공개 프로필 필요) |
| `check_exclude_auto.py` | IGDB 시리즈 정보로 다나와 제외 규칙 자동 생성 시험 |
| `check_phonetic_match.py` | 영어↔한글 발음 비교 보조 시험 |
| `check_llm_names.py`, `gen_gemini_names.py` | LLM 한국어 이름 후보 생성·평가 |
| `check_assign.py` | 상품→게임 배정(엘라스틱서치 방식 모의) 시험 |

## 실행 전
- 저장 위치는 `collector/samples/`입니다 (Git 제외). 키는 `collector/.env` 또는 환경 변수에서만 읽습니다.
- 필요한 환경 변수: ITAD_API_KEY, IGDB_CLIENT_ID, IGDB_CLIENT_SECRET, STEAM_API_KEY, GEMINI_API_DANAWA_NAME_GENERATE_KEY
- `pip install -r requirements.txt python-dotenv` 후 `python collector/experiments/check_candidates.py`
- 다나와는 요청 간격 10초 이상, robots.txt·약관을 지킵니다.
