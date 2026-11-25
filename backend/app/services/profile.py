"""내 정보(#3), Steam ID 연동(#4), 내 PC 사양(#30). users·user_specs는 Backend가 쓰는 테이블이다.

본인 데이터라서 Primary 세션으로 읽고 쓴다. 이메일·Steam ID는 로그에 남기지 않는다.
"""

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.clients import steam
from app.core.errors import ApiError, unavailable
from app.db.models import User, UserOwnedGame, UserSpec
from app.schemas.profile import SpecsBody, SpecsOut

log = logging.getLogger(__name__)

STEAM_ID_RE = re.compile(r"^\d{17}$")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # DB는 UTC naive


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "NOT_FOUND", "사용자를 찾을 수 없습니다")
    return user


def rename(db: Session, user_id: int, name: str) -> User:
    user = get_user(db, user_id)
    user.nickname = name
    db.commit()
    return user


def set_steam_id(db: Session, user_id: int, steam_id: str) -> tuple[str, int]:
    """Steam ID를 저장하고 보유 게임(appid·플레이 시간)을 Steam에서 가져와 통째로 갱신한다.

    Steam 조회가 실패하면 아무것도 저장하지 않는다(Steam ID도 그대로).
    돌려주는 값: (steam_id, 저장한 보유 게임 수). 같은 ID로 다시 부르면 새로 고침이 된다.
    """
    if not STEAM_ID_RE.fullmatch(steam_id):
        raise ApiError(400, "INVALID_STEAM_ID", "Steam ID는 17자리 숫자여야 합니다")
    user = get_user(db, user_id)
    try:
        owned = steam.get_owned_games(steam_id)
    except steam.SteamPrivateProfile:
        raise ApiError(
            400,
            "STEAM_PROFILE_PRIVATE",
            "Steam 프로필과 게임 세부 정보를 '공개'로 바꾼 뒤 다시 시도해 주세요",
        ) from None
    except steam.SteamUnavailable as exc:
        log.warning("Steam 조회 실패: %s", exc)  # 오류 종류만. ID·키는 남기지 않는다
        raise unavailable(
            "Steam에서 보유 게임을 가져오지 못했어요. 잠시 후 다시 시도해 주세요"
        ) from None
    now = _now()
    user.steam_id = steam_id
    db.execute(delete(UserOwnedGame).where(UserOwnedGame.user_id == user_id))
    db.add_all(
        UserOwnedGame(
            user_id=user_id,
            steam_appid=g.appid,
            playtime_forever_min=g.playtime_forever_min,
            rtime_last_played=g.rtime_last_played,
            updated_at=now,
        )
        for g in owned
    )
    db.commit()
    return steam_id, len(owned)


def _specs_out(row: UserSpec | None) -> SpecsOut:
    if row is None:
        return SpecsOut(cpu="", gpu="", ram_gb=None, os="")
    return SpecsOut(cpu=row.cpu or "", gpu=row.gpu or "", ram_gb=row.ram_gb, os=row.os or "")


def get_specs(db: Session, user_id: int) -> SpecsOut:
    return _specs_out(db.get(UserSpec, user_id))


def put_specs(db: Session, user_id: int, body: SpecsBody) -> SpecsOut:
    """네 항목을 통째로 바꾼다. 빈 문자열·null은 '미입력'으로 저장한다."""
    get_user(db, user_id)
    row = db.get(UserSpec, user_id)
    if row is None:
        row = UserSpec(user_id=user_id)
        db.add(row)
    row.cpu = (body.cpu or "").strip() or None
    row.gpu = (body.gpu or "").strip() or None
    row.ram_gb = body.ram_gb
    row.os = (body.os or "").strip() or None
    row.updated_at = _now()
    db.commit()
    return _specs_out(row)
