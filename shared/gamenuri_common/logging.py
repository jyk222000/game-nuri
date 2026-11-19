"""공통 로깅: 모든 서비스가 같은 형식으로 남긴다."""

import logging

from .config import get_settings

FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(level=get_settings().log_level, format=FORMAT)
    return logging.getLogger(name)
