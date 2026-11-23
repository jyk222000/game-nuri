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
