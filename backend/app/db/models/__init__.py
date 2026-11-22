from app.db.models.user import (
    Alert,
    AlertLog,
    NotificationSetting,
    User,
    UserOwnedGame,
    UserSpec,
    Wishlist,
)

# Backend가 쓰는 테이블. 가격·게임 테이블에는 쓰지 않는다 (Kafka Connect 담당).
WRITABLE_MODELS = (
    User,
    UserSpec,
    NotificationSetting,
    UserOwnedGame,
    Wishlist,
    Alert,
    AlertLog,
)

__all__ = [
    "WRITABLE_MODELS",
    "Alert",
    "AlertLog",
    "NotificationSetting",
    "User",
    "UserOwnedGame",
    "UserSpec",
    "Wishlist",
]
