"""게임 자동완성(#6)·검색(#5).

기본(`SEARCH_BACKEND=db`)은 MariaDB `games`·`game_aliases`만 읽는다. q는 영문명·한글명·별칭의
**부분 일치**(대소문자 무시)다. 별칭은 AI가 만든 것(source='llm')을 검수 여부와 상관없이
검색에 쓰지 않는다(팀 결정). igdb·manual 별칭만 쓴다.

`SEARCH_BACKEND=es`이면 검색(#5)에 한해 Elasticsearch `games` 인덱스(nori 형태소·오타 허용)를
**더한다.** ES가 찾은 game_id를 MariaDB 부분 일치 결과에 합치므로 결과가 db 방식보다 줄지
않는다(별칭도 그대로 MariaDB가 맡는다). 정렬·필터·카드는 기존 코드를 그대로 쓴다.
ES가 꺼져 있거나 늦거나(요청 2초 제한) 응답이 이상하면 경고만 남기고 db 방식으로 처리한다.
자동완성(#6)은 호출이 잦아 ES를 쓰지 않는다.
"""

import logging

from elasticsearch import ApiError, TransportError
from sqlalchemy import ColumnElement, case, func, or_, select
from sqlalchemy.orm import Session

from app.clients.es import get_es
from app.core.config import get_backend_settings
from app.db.models import Game, GameAlias, GameGenre, GamePlatform, GameTimeToBeat, Genre
from app.schemas.game import AutocompleteItem, Card
from app.services import cards, rankings

log = logging.getLogger(__name__)

ES_MAX_HITS = 500  # ES에서 받는 후보 수 (그 안에서 MariaDB가 필터·정렬·페이지를 처리한다)


def _escape(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contains(column, q: str) -> ColumnElement[bool]:  # noqa: ANN001
    return column.ilike(f"%{_escape(q)}%", escape="\\")


def _matches(q: str) -> ColumnElement[bool]:
    # AI가 만든 별칭(source='llm')은 검수 여부와 상관없이 검색에 쓰지 않는다 (팀 결정)
    usable_alias = select(GameAlias.game_id).where(
        _contains(GameAlias.alias, q), GameAlias.source != "llm"
    )
    return or_(_contains(Game.name, q), _contains(Game.name_ko, q), Game.game_id.in_(usable_alias))


def _prefix_rank(q: str):  # noqa: ANN202
    """이름이 q로 시작하는 게임을 먼저(0), 나머지는 그다음(1)."""
    p = f"{_escape(q)}%"
    return case(
        (or_(Game.name.ilike(p, escape="\\"), Game.name_ko.ilike(p, escape="\\")), 0), else_=1
    )


def _es_ranked_ids(q: str) -> list[int] | None:
    """ES가 찾은 game_id (점수 높은 순). 스위치가 db이거나 ES 호출이 실패하면 None → db 방식."""
    s = get_backend_settings()
    if s.search_backend != "es":
        return None
    # games(name·name_ko)와 game_aliases(alias)를 한 번에 찾는다. 두 인덱스 모두 game_id가 있다.
    fields = ["name^2", "name_ko^2", "alias^2"]
    try:
        result = get_es().search(
            index=f"{s.es_games_index},{s.es_aliases_index}",
            ignore_unavailable=True,  # 별칭 인덱스가 아직 없어도 오류 없이 games만 검색한다
            size=ES_MAX_HITS,
            query={
                "bool": {
                    "should": [
                        # 형태소 단위 일치 + 오타 허용 ("엘든링을" ~ "엘든 링", "elden rnig")
                        {"multi_match": {"query": q, "fields": fields, "fuzziness": "AUTO"}},
                        # 입력 중인 마지막 단어 접두 일치 ("elden r" → "Elden Ring")
                        {"multi_match": {"query": q, "fields": fields, "type": "phrase_prefix"}},
                    ],
                    "minimum_should_match": 1,
                    # AI가 만든 별칭(source=llm)은 검수 여부와 상관없이 뺀다 (MariaDB와 같다)
                    "must_not": [{"term": {"source": "llm"}}],
                }
            },
            source_includes=["game_id"],
        )
        ids: list[int] = []
        for hit in result["hits"]["hits"]:
            gid = int(hit["_source"]["game_id"])
            if gid not in ids:
                ids.append(gid)
        return ids
    except (ApiError, TransportError, KeyError, TypeError, ValueError) as exc:
        log.warning("게임 검색 ES 실패, MariaDB로 대체: %s", type(exc).__name__)
        return None


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
    """(해당 페이지 카드, 전체 건수). sort가 없으면 q가 있을 때 접두 일치 먼저, 그다음 이름순
    (ES 방식이면 ES 점수 순이 먼저).

    length(short|medium|long)는 '보통' 클리어 시간 구간 조건이다. 시간 정보가 없는 게임은 빠진다.
    """
    where: list[ColumnElement[bool]] = []
    if length:
        where.append(
            Game.game_id.in_(select(GameTimeToBeat.game_id).where(rankings.length_filter(length)))
        )
    es_ids = _es_ranked_ids(q) if q else None  # None이면 MariaDB 부분 일치만 쓴다
    if q:
        match = _matches(q)
        if es_ids:  # ES가 더 찾은 게임(오타·형태소)을 합친다. 부분 일치 결과는 그대로 남는다
            match = or_(match, Game.game_id.in_(es_ids))
        where.append(match)
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

    if es_ids:  # sort가 없을 때의 순서: ES 점수 순, 그 밖은 뒤에 (안정 정렬이라 이름순 유지)
        es_rank = {gid: n for n, gid in enumerate(es_ids)}
        ids.sort(key=lambda i: es_rank.get(i, len(es_rank)))

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
