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
    critic_score: int | None  # IGDB 평론가 집계 점수(0~100, 반올림). 메타크리틱이 아니다
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


class RelatedGame(BaseModel):
    """관련 게임(시리즈·DLC·에디션)을 가볍게 가리키는 항목."""

    game_id: int
    name: str  # name_ko 우선, 없으면 games.name
    cover_url: str | None


class SeriesOut(BaseModel):
    kind: str  # collection | franchise
    name: str
    games: list[RelatedGame]  # 같은 시리즈의 다른 게임(최대 12개, 출시일순)


class ReviewStatsOut(BaseModel):
    """Steam 스토어 리뷰 등급·수. 한국어(스토어 표시값)와 전체 언어를 따로 둔다."""

    label_ko: str | None  # 예: 대체로 긍정적
    count_ko: int | None
    positive_pct_ko: int | None  # 0~100
    score_ko: int | None  # Steam 등급 1~9
    label_all: str | None
    count_all: int | None
    positive_pct_all: int | None


class TimeToBeat(BaseModel):
    """IGDB 클리어 시간 3종(시간, 소수 첫째 자리)과 집계 인원. 값이 0이거나 없으면 그 값만 null."""

    hastily_hours: float | None  # 빠르게
    normally_hours: float | None  # 보통
    completely_hours: float | None  # 완벽하게
    count: int | None  # 집계 인원


class GameDetail(Card):
    """상세 = 카드 필드 + 아래 (docs/contracts/api.md)."""

    time_to_beat: TimeToBeat | None  # game_time_to_beat 행이 없으면 null
    critic_count: int | None  # IGDB 평론 집계 수(critic_score는 카드 필드)
    user_score: int | None  # IGDB 사용자 평점(0~100, 반올림)
    user_score_count: int | None  # IGDB 사용자 평가 수
    korean_supported: bool | None  # Steam 지원 언어에 한국어가 있는가. 모르면 null
    age_rating: int | None  # Steam required_age(0=제한 없음). 모르면 null
    developers: list[str]
    publishers: list[str]
    series: list[SeriesOut]
    parent_game: RelatedGame | None  # DLC·확장이면 본편
    version_parent: RelatedGame | None  # 에디션이면 원본
    dlcs: list[RelatedGame]
    editions: list[RelatedGame]
    review_stats: ReviewStatsOut | None  # game_review_stats 행이 없으면 null
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


class RecommendationCard(Card):
    """추천(#23) 카드: 카드 + 추천 이유."""

    reason: str


class RecommendationsOut(BaseModel):
    items: list[RecommendationCard]
