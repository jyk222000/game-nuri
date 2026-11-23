"""게임 카드 (docs/contracts/api.md '카드'). 목록 API들이 공통으로 쓴다."""

from pydantic import BaseModel


class Card(BaseModel):
    game_id: int
    name: str  # name_ko 우선, 없으면 games.name
    name_en: str  # games.name
    genres: list[str]
    platforms: list[str]  # ERD 코드 (PC, PS5 ...). 표시 이름은 프런트가 바꾼다
    cover_url: str | None
    price_krw: int | None  # 새 상품 중 현재 최저가 (prices_current)
    regular_krw: int | None
    discount_pct: int | None
    positive_ratio: float | None
    concurrent_players: int | None
    time_to_beat_hours: int | None
    wished: bool


class NameListOut(BaseModel):
    items: list[str]


class AutocompleteItem(BaseModel):
    game_id: int
    name: str  # name_ko 우선, 없으면 games.name
    name_en: str


class AutocompleteOut(BaseModel):
    items: list[AutocompleteItem]


class SearchOut(BaseModel):
    items: list[Card]
    total: int
    page: int
    size: int


class CardsOut(BaseModel):
    items: list[Card]


class GameDetail(Card):
    """상세 = 카드 필드 + 아래 (docs/contracts/api.md)."""

    release_date: str | None  # YYYY-MM-DD
    summary: str | None
    tags: list[str]
    online_only: bool  # games.is_online (멀티플레이어 등, ⑦ 경고용)
    steam_app_id: int | None  # game_store_ids(store='steam')
    lowest_krw: int | None  # 새 상품 역대 최저가 (이력·현재가 중 최저)
    insights: list[dict]  # analysis가 만드는 태그. 모양이 정해질 때까지 항상 빈 목록


class WarningCard(Card):
    """접속자 적은 온라인 게임(#33) 카드: 카드 + 경고 문구."""

    warning: str


class WarningCardsOut(BaseModel):
    items: list[WarningCard]
