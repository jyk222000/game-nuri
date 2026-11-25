"""내 취향 프로필(#24)과 플레이타임 기반 추천(#23).

데이터: `user_owned_games`(Steam 보유 게임·플레이 시간, collector가 채움)를 `game_store_ids`
(store='steam', external_id=앱 ID)로 `game_id`에 연결하고, 게임의 장르(`game_genres`)별로
플레이 시간을 모은다. 본인 데이터라 Primary 세션으로 읽는다.

Steam ID를 연동하지 않았으면 400 STEAM_REQUIRED. 연동했지만 보유 게임을 아직 못 가져왔으면
빈 결과(0·빈 목록)다. `style` 문장과 추천 순위는 **임시 규칙**이다 (분석·AI 담당과 확정 전).
"""

from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import (
    GameGenre,
    GameStoreId,
    GameTimeToBeat,
    Genre,
    UserOwnedGame,
    Wishlist,
)
from app.schemas.game import RecommendationCard
from app.schemas.me import TasteGenre, TasteOut
from app.services import cards, profile, rankings, ratings

TOP_GENRES = 5  # 취향 프로필에 보여 줄 장르 수
RECOMMEND_FROM_GENRES = 3  # 추천 후보를 모을 상위 장르 수
NO_DATA_STYLE = "아직 취향을 분석할 데이터가 부족해요"
PREFERRED_LENGTH_MIN_GAMES = (
    5  # 선호 플레이 길이를 판단하려면 클리어 시간이 있는 플레이한 게임이 이만큼 필요(임시)
)


@dataclass
class Taste:
    total_minutes: int
    owned_count: int
    owned_game_ids: set[int]
    genre_minutes: dict[int, int]  # genre_id -> 플레이 분
    genre_names: dict[int, str]
    minutes_by_game: dict[int, int]  # game_id -> 플레이 분 (games에 연결된 보유 게임만)


def _require_steam(db: Session, user_id: int) -> None:
    if not profile.get_user(db, user_id).steam_id:
        raise ApiError(400, "STEAM_REQUIRED", "Steam ID를 먼저 연동해 주세요")


def _load(db: Session, user_id: int) -> Taste:
    owned = db.execute(
        select(UserOwnedGame.steam_appid, UserOwnedGame.playtime_forever_min).where(
            UserOwnedGame.user_id == user_id
        )
    ).all()
    minutes_by_app = {app: minutes or 0 for app, minutes in owned}

    game_by_app: dict[int, int] = {}
    if minutes_by_app:
        for gid, ext in db.execute(
            select(GameStoreId.game_id, GameStoreId.external_id).where(
                GameStoreId.store == "steam",
                GameStoreId.external_id.in_([str(a) for a in minutes_by_app]),
            )
        ):
            game_by_app[int(ext)] = gid
    minutes_by_game = {game_by_app[a]: m for a, m in minutes_by_app.items() if a in game_by_app}

    genre_minutes: dict[int, int] = defaultdict(int)
    names: dict[int, str] = {}
    if minutes_by_game:
        for gid, genre_id, name in db.execute(
            select(GameGenre.game_id, GameGenre.genre_id, Genre.name)
            .join(Genre, Genre.genre_id == GameGenre.genre_id)
            .where(GameGenre.game_id.in_(list(minutes_by_game)))
        ):
            genre_minutes[genre_id] += minutes_by_game[gid]
            names[genre_id] = name
    return Taste(
        total_minutes=sum(minutes_by_app.values()),
        owned_count=len(minutes_by_app),
        owned_game_ids=set(minutes_by_game),
        genre_minutes=dict(genre_minutes),
        genre_names=names,
        minutes_by_game=minutes_by_game,
    )


def _preferred_length(db: Session, t: Taste) -> Literal["short", "medium", "long"] | None:
    """플레이한 보유 게임(0분 초과)의 '보통' 클리어 시간 중앙값이 속한 구간.

    평균은 수백 시간짜리 한두 게임에 크게 흔들려서 중앙값을 쓴다. 클리어 시간이 있는 게임이
    PREFERRED_LENGTH_MIN_GAMES개 미만이면 판단하지 않고 None이다.
    """
    played = [gid for gid, minutes in t.minutes_by_game.items() if minutes > 0]
    if not played:
        return None
    seconds = [
        s
        for s in db.scalars(
            select(GameTimeToBeat.normally_sec).where(
                GameTimeToBeat.game_id.in_(played), GameTimeToBeat.normally_sec > 0
            )
        )
        if s
    ]
    if len(seconds) < PREFERRED_LENGTH_MIN_GAMES:
        return None
    return rankings.length_bucket(median(seconds))


def _ranked_genres(t: Taste) -> list[int]:
    """플레이 시간이 많은 순 (0분 장르는 뺀다)."""
    return [
        g
        for g, m in sorted(t.genre_minutes.items(), key=lambda kv: (-kv[1], t.genre_names[kv[0]]))
        if m > 0
    ]


def get_taste(db: Session, user_id: int) -> TasteOut:
    _require_steam(db, user_id)
    t = _load(db, user_id)
    ranked = _ranked_genres(t)
    total = sum(t.genre_minutes[g] for g in ranked)
    top = [
        TasteGenre(genre=t.genre_names[g], pct=round(t.genre_minutes[g] * 100 / total))
        for g in ranked[:TOP_GENRES]
    ]
    style = f"{'·'.join(x.genre for x in top[:2])} 장르를 즐기는 플레이어" if top else NO_DATA_STYLE
    return TasteOut(
        total_playtime_hours=round(t.total_minutes / 60),
        owned_games=t.owned_count,
        top_genres=top,
        style=style,
        preferred_length=_preferred_length(db, t),
    )


def recommend(db: Session, user_id: int, size: int) -> list[RecommendationCard]:
    """상위 장르 게임 중 아직 없는(보유하지 않은) 게임을 점수 높은 순으로.

    점수 = 장르 비중(내 플레이 시간이 가장 많은 장르 대비) × 긍정 비율. 평점만으로 줄을 세우면
    플레이 시간이 적은 장르의 고평점 게임이 위를 차지하므로 장르 비중을 곱한다.
    reason은 그 게임이 속한 장르 중 내 플레이 시간이 가장 많은 장르 기준이다.
    """
    _require_steam(db, user_id)
    t = _load(db, user_id)
    top = _ranked_genres(t)[:RECOMMEND_FROM_GENRES]
    if not top:
        return []
    rows = db.execute(
        select(GameGenre.game_id, GameGenre.genre_id).where(GameGenre.genre_id.in_(top))
    ).all()
    best_genre: dict[int, int] = {}
    for gid, genre_id in rows:
        if gid in t.owned_game_ids:
            continue
        if gid not in best_genre or t.genre_minutes[genre_id] > t.genre_minutes[best_genre[gid]]:
            best_genre[gid] = genre_id
    known = ratings.positive_ratios(db, best_genre)
    top_minutes = t.genre_minutes[top[0]]
    # 평가 없는 게임은 점수 대신 -1로 뒤에 둔다
    score = {
        gid: t.genre_minutes[genre_id] / top_minutes * known[gid] if gid in known else -1.0
        for gid, genre_id in best_genre.items()
    }
    ids = sorted(best_genre, key=lambda g: (-score[g], g))[:size]
    wished = set(db.scalars(select(Wishlist.game_id).where(Wishlist.user_id == user_id)))
    built = cards.build_cards(db, ids, wished_ids=wished)
    return [
        RecommendationCard(
            **c.model_dump(),
            reason=f"{t.genre_names[best_genre[c.game_id]]} 장르를 많이 플레이했어요",
        )
        for c in built
    ]
