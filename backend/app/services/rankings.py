"""목록형 추천: 인기(#9), 짧게 끝낼 게임(#25), 동접자 상위(#32)·접속자 적은 온라인 게임(#33).

모두 읽기 전용이고 로그인 없이 보는 목록이라 카드의 wished는 false다.
**기준값은 임시**이며 아래 상수만 고치면 된다 (팀 확정 전).
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Game, GameTimeToBeat, PlayerCount, Wishlist
from app.schemas.game import Card, WarningCard
from app.services import cards

SHORT_MAX_SEC = 10 * 3600  # '짧게 끝낼 게임': 보통 플레이 시간이 10시간 이하
LOW_PLAYERS_MAX = 1000  # '접속자가 적다': 가장 최근 동접자가 이 값 미만
LOW_PLAYERS_WARNING = "접속자가 적어 매칭이 어려울 수 있어요"


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


def popular(db: Session, size: int) -> list[Card]:
    """인기 = 찜한 사용자 수가 많은 순, 같으면 동접자 많은 순. 찜도 동접자도 없으면 제외."""
    wishes = dict(
        db.execute(select(Wishlist.game_id, func.count()).group_by(Wishlist.game_id)).all()
    )
    players = latest_players(db)
    ids = {i for i in set(wishes) | set(players) if wishes.get(i, 0) > 0 or players.get(i, 0) > 0}
    ranked = sorted(ids, key=lambda i: (-wishes.get(i, 0), -players.get(i, 0), i))
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
