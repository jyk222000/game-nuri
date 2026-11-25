"""게임 자동완성(#6)·검색(#5). MariaDB `games`·`game_aliases`만 읽는다 (임시 구현).

q는 영문명·한글명·별칭의 **부분 일치**(대소문자 무시)다. 오타 허용·형태소 검색은 Elasticsearch
`games` 인덱스가 필요하다(인덱스 이름·필드는 남현식과 확정 전이라 아직 연결하지 않았다).
별칭은 AI가 만든 것(source='llm')이 검수(reviewed) 전이면 검색에 쓰지 않는다(erd.sql 규칙).
"""

from sqlalchemy import ColumnElement, case, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Game, GameAlias, GameGenre, GamePlatform, GameTimeToBeat, Genre
from app.schemas.game import AutocompleteItem, Card
from app.services import cards, rankings


def _escape(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contains(column, q: str) -> ColumnElement[bool]:  # noqa: ANN001
    return column.ilike(f"%{_escape(q)}%", escape="\\")


def _matches(q: str) -> ColumnElement[bool]:
    usable_alias = select(GameAlias.game_id).where(
        _contains(GameAlias.alias, q), or_(GameAlias.reviewed.is_(True), GameAlias.source != "llm")
    )
    return or_(_contains(Game.name, q), _contains(Game.name_ko, q), Game.game_id.in_(usable_alias))


def _prefix_rank(q: str):  # noqa: ANN202
    """이름이 q로 시작하는 게임을 먼저(0), 나머지는 그다음(1)."""
    p = f"{_escape(q)}%"
    return case(
        (or_(Game.name.ilike(p, escape="\\"), Game.name_ko.ilike(p, escape="\\")), 0), else_=1
    )


def autocomplete(db: Session, q: str, limit: int) -> list[AutocompleteItem]:
    if not q:  # 공백만 입력하면 전부 일치하므로 빈 목록
        return []
    rows = db.execute(
        select(Game.game_id, Game.name, Game.name_ko)
        .where(_matches(q))
        .order_by(_prefix_rank(q), func.length(Game.name), Game.name, Game.game_id)
        .limit(limit)
    ).all()
    return [AutocompleteItem(game_id=gid, name=ko or name, name_en=name) for gid, name, ko in rows]


def search(
    db: Session,
    q: str | None,
    platform: str | None,
    genre: str | None,
    sort: str | None,
    page: int,
    size: int,
    length: str | None = None,
) -> tuple[list[Card], int]:
    """(해당 페이지 카드, 전체 건수). sort가 없으면 q가 있을 때 접두 일치 먼저, 그다음 이름순.

    length(short|medium|long)는 '보통' 클리어 시간 구간 조건이다. 시간 정보가 없는 게임은 빠진다.
    """
    where: list[ColumnElement[bool]] = []
    if length:
        where.append(
            Game.game_id.in_(select(GameTimeToBeat.game_id).where(rankings.length_filter(length)))
        )
    if q:
        where.append(_matches(q))
    if platform:
        where.append(
            Game.game_id.in_(select(GamePlatform.game_id).where(GamePlatform.platform == platform))
        )
    if genre:
        where.append(
            Game.game_id.in_(
                select(GameGenre.game_id)
                .join(Genre, Genre.genre_id == GameGenre.genre_id)
                .where(Genre.name == genre)
            )
        )
    total = db.scalar(select(func.count()).select_from(Game).where(*where)) or 0

    order = [_prefix_rank(q)] if q else []
    order += [Game.name, Game.game_id]
    ids = [r[0] for r in db.execute(select(Game.game_id).where(*where).order_by(*order))]

    if sort in ("price", "discount"):
        # 현재가는 prices_current에서 구해 파이썬에서 정렬한다 (가격이 없는 게임은 뒤로).
        prices = cards.lowest_new_prices(db, ids)
        if sort == "price":
            key = lambda i: (i not in prices, prices[i].price_krw if i in prices else 0, i)  # noqa: E731
        else:
            key = lambda i: (  # noqa: E731
                i not in prices or not prices[i].discount_pct,
                -(prices[i].discount_pct or 0) if i in prices else 0,
                i,
            )
        ids.sort(key=key)
    elif sort == "popular":
        # 인기 게임(#9)과 같은 순서. 찜·동접자가 없는 게임은 제외하지 않고 뒤에 이름순으로 둔다
        # (ids는 이미 이름순이고 sort는 안정 정렬이라 같은 칸 안에서 그 순서가 유지된다).
        rank = {gid: n for n, gid in enumerate(rankings.popularity_order(db))}
        ids.sort(key=lambda i: rank.get(i, len(rank)))
    elif sort == "rating":
        # 평론가 점수 높은 순(카드에 보이는 반올림 점수), 같으면 평론 수 많은 순.
        # 점수가 없는 게임은 제외하지 않고 맨 뒤에 이름순(ids가 이미 이름순, 안정 정렬).
        scores = {
            gid: (cards.critic_score(rating), count or 0)
            for gid, rating, count in db.execute(
                select(Game.game_id, Game.aggregated_rating, Game.aggregated_rating_count).where(
                    Game.game_id.in_(ids), Game.aggregated_rating.is_not(None)
                )
            )
        }
        ids.sort(key=lambda i: (i not in scores, *(-v for v in scores.get(i, (0, 0)))))

    start = (page - 1) * size
    return cards.build_cards(db, ids[start : start + size], wished_ids=set()), total
