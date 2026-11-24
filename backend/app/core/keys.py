"""Valkey 키 규칙과 TTL. 키 이름·TTL은 여기 한 곳에서만 정한다 (backend/CLAUDE.md 기준).

TTL 값 중 '제안'은 팀장이 확정하기 전의 임시 값이다.
"""

# ---------- 키 ----------
SESSION_COOKIE_NAME = "gamenuri_session"  # 제안: 세션 쿠키 이름


def session_key(session_id: str) -> str:
    """세션. 값은 user_id 문자열 (로그인 구현자와 맞출 인터페이스)."""
    return f"session:{session_id}"


def price_cache_key(game_id: int) -> str:
    return f"cache:prices:{game_id}"


def trending_cache_key() -> str:
    """실시간 검색어 결과 캐시 (ES 호출을 줄인다)."""
    return "cache:search:trending"


def alert_sent_key(alert_id: int, price_krw: int) -> str:
    """같은 알림을 같은 가격으로 두 번 보내지 않기 위한 중복 방지 키."""
    return f"alert_sent:{alert_id}:{price_krw}"


def spec_check_key(game_id: int, spec_hash: str) -> str:
    """사양 적합도 AI 판정 결과 캐시 (⑥)."""
    return f"spec_check:{game_id}:{spec_hash}"


# ---------- TTL (초) ----------
PRICE_CACHE_TTL_SECONDS = 10 * 60  # 확정: 가격 캐시 10분 (backend/CLAUDE.md)
TRENDING_CACHE_TTL_SECONDS = 60  # 제안: 실시간 검색어는 1분만 저장
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60  # 제안: 7일
ALERT_SENT_TTL_SECONDS = 24 * 60 * 60  # 제안: 24시간 (같은 가격 알림 재발송 방지 기간)
SPEC_CHECK_TTL_SECONDS = 7 * 24 * 60 * 60  # 제안: 7일 (사양이 바뀌면 hash가 달라져 새로 판정)
