"""읽기 전용 테이블 쓰기 가드.

가격·게임 테이블(READ_ONLY_MODELS)은 Kafka Connect만 쓴다. ORM으로 이 모델 객체를
add·update·delete 하면 flush 시점에 예외를 낸다.

이것은 안전장치일 뿐이다. 진짜 방어선은 DB 권한(gamenuri_app은 사용자 테이블에만 쓰기)이다.
`session.execute(insert(...))` 같은 직접 SQL은 잡지 못한다.
테스트 데이터를 넣을 때만 `session.info[ALLOW_READONLY_WRITE] = True`로 끈다.
"""

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import READ_ONLY_MODELS

ALLOW_READONLY_WRITE = "allow_readonly_write"


class ReadOnlyTableWriteError(RuntimeError):
    """읽기 전용 테이블에 쓰려 했다."""


def _check(kind: str, obj: object) -> None:
    if isinstance(obj, READ_ONLY_MODELS):
        table = type(obj).__tablename__
        raise ReadOnlyTableWriteError(f"읽기 전용 테이블 {table}에는 {kind}할 수 없습니다")


@event.listens_for(Session, "before_flush")
def _block_readonly_writes(session: Session, flush_context, instances) -> None:  # noqa: ANN001
    if session.info.get(ALLOW_READONLY_WRITE):
        return
    for obj in session.new:
        _check("추가", obj)
    for obj in session.dirty:
        if session.is_modified(obj):
            _check("수정", obj)
    for obj in session.deleted:
        _check("삭제", obj)
