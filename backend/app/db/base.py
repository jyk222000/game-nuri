from sqlalchemy import BigInteger, Integer
from sqlalchemy.orm import DeclarativeBase

# MariaDB는 BIGINT, 테스트용 SQLite는 INTEGER여야 자동 증가 기본키가 동작한다.
BigIntPk = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    """모든 모델의 부모. 컬럼 이름·타입은 docs/contracts/erd.sql 그대로 따른다."""
