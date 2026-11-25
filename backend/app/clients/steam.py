"""Steam Web API 클라이언트: 보유 게임(GetOwnedGames)만 조회한다 (#4 Steam 연동).

- API 키는 STEAM_KEY 환경 변수(Settings.steam_key)에서만 읽는다. 키는 요청 주소에 붙으므로
  오류 객체를 그대로 로그에 남기지 않는다(주소에 키가 섞인다). 오류 종류 이름만 남긴다.
- 프로필·게임 세부 정보가 비공개면 Steam은 빈 응답(`{"response": {}}`)을 준다.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from gamenuri_common.config import get_settings

OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
TIMEOUT_SECONDS = 5.0


class SteamUnavailable(Exception):
    """키가 없거나, 연결·응답이 정상이 아닐 때."""


class SteamPrivateProfile(Exception):
    """프로필 또는 게임 세부 정보가 비공개라 보유 게임을 볼 수 없을 때."""


@dataclass(frozen=True)
class OwnedGame:
    appid: int
    playtime_forever_min: int
    rtime_last_played: datetime | None = None  # 마지막 플레이 시각(UTC, naive). 기록이 없으면 None


def get_owned_games(steam_id: str) -> list[OwnedGame]:
    key = get_settings().steam_key
    if not key:
        raise SteamUnavailable("STEAM_KEY 미설정")
    try:
        resp = httpx.get(
            OWNED_GAMES_URL,
            params={
                "key": key,
                "steamid": steam_id,
                "include_played_free_games": 1,
                "format": "json",
            },
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        body = resp.json().get("response", {})
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise SteamUnavailable(type(exc).__name__) from None  # 주소(키 포함)가 새지 않게 끊는다
    if "game_count" not in body:  # 비공개는 빈 응답. 공개인데 게임이 0개면 game_count가 0이다.
        raise SteamPrivateProfile
    games: dict[int, OwnedGame] = {}
    for g in body.get("games", []):
        try:
            appid = int(g["appid"])
            minutes = max(int(g.get("playtime_forever", 0)), 0)
        except (KeyError, TypeError, ValueError):
            continue
        games[appid] = OwnedGame(appid, minutes, _last_played(g.get("rtime_last_played")))
    return list(games.values())


def _last_played(value: object) -> datetime | None:
    """Steam의 rtime_last_played(유닉스 초)를 UTC naive 시각으로. 0·없음·이상한 값은 None."""
    try:
        seconds = int(value)  # type: ignore[call-overload]
        return datetime.fromtimestamp(seconds, UTC).replace(tzinfo=None) if seconds > 0 else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None
