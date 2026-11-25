"""목록형 추천: 인기(#9), 짧게 끝낼 게임(#25), 동접자 상위(#32)·접속자 적은 온라인 게임(#33).

모두 읽기 전용이고 로그인 없이 보는 목록이라 카드의 wished는 false다.
**기준값은 임시**이며 아래 상수만 고치면 된다 (팀 확정 전).
"""

from typing import Literal

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import Session

from app.db.models import Game, GameTimeToBeat, PlayerCount, Wishlist
from app.schemas.game import Card, WarningCard
from app.services import cards, deals

SHORT_MAX_SEC = 10 * 3600  # '짧게 끝낼 게임': 보통 플레이 시간이 10시간 이하
MEDIUM_MAX_SEC = (
    40 * 3600
)  # 클리어 시간 구간: 10시간 초과~40시간 이하 = 보통, 초과 = 길게 (임시 기준)
LOW_PLAYERS_MAX = 1000  # '접속자가 적다': 가장 최근 동접자가 이 값 미만
LOW_PLAYERS_WARNING = "접속자가 적어 매칭이 어려울 수 있어요"


def length_bucket(normally_sec: float | None) -> Literal["short", "medium", "long"] | None:
    """'보통' 클리어 시간(초)이 속한 구간. 시간 정보가 없거나 0이면 None."""
    if not normally_sec or normally_sec <= 0:
        return None
    if normally_sec <= SHORT_MAX_SEC:
        return "short"
    return "medium" if normally_sec <= MEDIUM_MAX_SEC else "long"


def length_filter(length: str) -> ColumnElement[bool]:
    """game_time_to_beat.normally_sec 구간 조건. 시간 정보가 없는 게임(없음·0)은 걸러진다."""
    col = GameTimeToBeat.normally_sec
    if length == "short":
        return and_(col > 0, col <= SHORT_MAX_SEC)
    if length == "medium":
        return and_(col > SHORT_MAX_SEC, col <= MEDIUM_MAX_SEC)
    return col > MEDIUM_MAX_SEC


def latest_players(db: Session) -> dict[int, int]:
    """게임별 가장 최근 동접자 수."""
    latest = (
        select(PlayerCount.game_id, func.max(PlayerCount.collected_at).label("t"))
        .group_by(PlayerCount.game_id)
        .subquery()
    )
    rows = db.execute(
        select(PlayerCount.game_id, PlayerCount.player_count).join(
            latest,
            (PlayerCount.game_id == latest.c.game_id) & (PlayerCount.collected_at == latest.c.t),
        )
    ).all()
    return {gid: n for gid, n in rows}


def popularity_order(db: Session) -> list[int]:
    """인기 순서의 게임 ID. 찜한 사용자 수가 많은 순, 같으면 동접자 많은 순, 그다음 game_id 순.

    찜도 동접자도 없는 게임은 담지 않는다(호출하는 쪽이 뒤에 붙인다).
    인기 게임(#9)과 게임 목록의 sort=popular가 같은 기준을 쓰도록 한 곳에 둔다.
    """
    wishes = dict(
        db.execute(select(Wishlist.game_id, func.count()).group_by(Wishlist.game_id)).all()
    )
    players = latest_players(db)
    ids = {i for i in set(wishes) | set(players) if wishes.get(i, 0) > 0 or players.get(i, 0) > 0}
    return sorted(ids, key=lambda i: (-wishes.get(i, 0), -players.get(i, 0), i))


def popular(db: Session, size: int) -> list[Card]:
    """인기 = 찜한 사용자 수가 많은 순, 같으면 동접자 많은 순.

    찜도 동접자도 있는 게임이 하나도 없으면 최근 할인 게임(할인율 큰 순)으로 대신한다.
    """
    ranked = popularity_order(db)
    if not ranked:  # 찜도 동접자도 없으면 최근 할인 게임으로 대신 채운다
        return deals.get_deals(db, size)
    return cards.build_cards(db, ranked[:size], wished_ids=set())


def short_games(db: Session, size: int) -> list[Card]:
    """보통 플레이 시간이 SHORT_MAX_SEC 이하인 게임, 짧은 순."""
    ids = [
        r[0]
        for r in db.execute(
            select(GameTimeToBeat.game_id)
            .where(GameTimeToBeat.normally_sec > 0, GameTimeToBeat.normally_sec <= SHORT_MAX_SEC)
            .order_by(GameTimeToBeat.normally_sec, GameTimeToBeat.game_id)
            .limit(size)
        )
    ]
    return cards.build_cards(db, ids, wished_ids=set())


def top_players(db: Session, size: int) -> list[Card]:
    players = latest_players(db)
    ranked = sorted((i for i, n in players.items() if n > 0), key=lambda i: (-players[i], i))
    return cards.build_cards(db, ranked[:size], wished_ids=set())


def low_players(db: Session, size: int) -> list[WarningCard]:
    """온라인 게임(games.is_online)인데 동접자가 LOW_PLAYERS_MAX 미만인 게임, 적은 순."""
    players = latest_players(db)
    online = set(db.scalars(select(Game.game_id).where(Game.is_online.is_(True))))
    low = sorted(
        (i for i, n in players.items() if i in online and n < LOW_PLAYERS_MAX),
        key=lambda i: (players[i], i),
    )
    built = cards.build_cards(db, low[:size], wished_ids=set())
    return [WarningCard(**c.model_dump(), warning=LOW_PLAYERS_WARNING) for c in built]
