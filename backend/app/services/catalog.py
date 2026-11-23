"""장르·태그 목록(#8). genres·tags는 읽기만 한다."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Genre, Tag


def genre_names(db: Session) -> list[str]:
    """필터에 쓰는 장르 이름(IGDB 영문 이름 그대로, 카드의 genres와 같은 값), 이름순."""
    return list(db.scalars(select(Genre.name).order_by(Genre.name)))


def tag_names(db: Session) -> list[str]:
    """태그 표시 이름: name_ko가 있으면 그것, 없으면 name. 중복은 한 번만, 이름순."""
    rows = db.execute(select(Tag.name, Tag.name_ko)).all()
    return sorted({ko or name for name, ko in rows})
