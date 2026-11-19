"""부하 테스트 (요구사항 #4). 실행: locust -f scripts/load/locustfile.py --host https://<도메인>

목적: ① FE·BE 2대로 요청이 고르게 나뉘는지 ② 병목 지점(DB, ES, Backend) ③ Valkey 캐시 전후 응답 시간
"""

import random

from locust import HttpUser, between, task

GAME_IDS = [119133, 1942, 1020, 7346]  # 실제 데이터의 game_id로 교체
QUERIES = ["엘든", "젤다", "사이버펑크", "몬헌", "발더스"]


class Visitor(HttpUser):
    wait_time = between(1, 3)

    @task(4)
    def search(self) -> None:
        self.client.get("/api/games", params={"q": random.choice(QUERIES)}, name="/api/games?q")

    @task(3)
    def prices(self) -> None:
        self.client.get(
            f"/api/games/{random.choice(GAME_IDS)}/prices", name="/api/games/{id}/prices"
        )

    @task(2)
    def trending(self) -> None:
        self.client.get("/api/search/trending")

    @task(1)
    def deals(self) -> None:
        self.client.get("/api/games/deals")
