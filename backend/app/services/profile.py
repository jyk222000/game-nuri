"""내 정보(#3), Steam ID 연동(#4), 내 PC 사양(#30). users·user_specs는 Backend가 쓰는 테이블이다.

본인 데이터라서 Primary 세션으로 읽고 쓴다. 이메일·Steam ID는 로그에 남기지 않는다.
"""

import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import User, UserSpec
from app.schemas.profile import SpecsBody, SpecsOut

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


def set_steam_id(db: Session, user_id: int, steam_id: str) -> str:
    if not STEAM_ID_RE.fullmatch(steam_id):
        raise ApiError(400, "INVALID_STEAM_ID", "Steam ID는 17자리 숫자여야 합니다")
    user = get_user(db, user_id)
    user.steam_id = steam_id
    db.commit()
    return steam_id


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
