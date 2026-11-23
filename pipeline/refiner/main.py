"""raw.* 소비 → 정제 → refined.* 발행.  python -m refiner.main

두 가지 방법으로 실행한다.

  1) 파일 시험 (Kafka 접속 없음. 시험은 이걸로)
     python -m refiner.main --dry-run --input raw.jsonl --id-map id_map.json --out out/
     (raw.jsonl 은 봉투 JSON 한 줄씩. kind 로 price·console_price·game_info·app_details 를 나눈다)

  2) Kafka 모드 (kafka1~3에서 서비스 refiner 로 실행. 설정은 환경변수)
     python -m refiner.main
       KAFKA_BOOTSTRAP            kafka1:9092,kafka2:9092,kafka3:9092   (필수)
       ID_MAP_PATH                시작 대응표 JSON 경로 (읽기만 한다)
       RATES_PATH                 월별 환율 JSON (기본 refiner/rates_monthly.json)
       ID_MAP_STATE_PATH          배운 대응표를 저장할 경로
                                  (예: /var/lib/game-nuri/refiner_id_map.json)
                                  비우면 저장하지 않는다 (재시작하면 다시 배워야 함)
       REFINER_TOPICS_IN          기본 raw.price,raw.console,raw.igdb,raw.steam
       REFINER_TOPIC_PRICES       기본 refined.prices
       REFINER_TOPIC_GAMES        기본 refined.games
       REFINER_TOPIC_REQUIREMENTS 기본 refined.requirements
       REFINER_TOPIC_UNMATCHED    기본 refined.unmatched

실제 토픽에는 시험 메시지를 넣지 않는다 (Kafka 구축 문서 5장 1번).
"""

from __future__ import annotations

import argparse
import json
import os
from contextlib import ExitStack
from pathlib import Path
from typing import Any

try:
    from gamenuri_common.logging import get_logger
except ImportError:  # 공통 패키지 의존성이 없는 환경(내 PC 시험)에서만
    import logging

    def get_logger(name: str) -> logging.Logger:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        return logging.getLogger(name)


from refiner.router import OUT_TOPICS, Maps, route
from refiner.rules.rates import RateBook

log = get_logger("refiner")


def topics() -> dict[str, Any]:
    """입력 토픽 목록과 출력 토픽 이름 (환경변수로 바꿀 수 있다)."""
    return {
        "in": os.environ.get("REFINER_TOPICS_IN", "raw.price,raw.console,raw.igdb,raw.steam").split(
            ","
        ),
        **{
            name: os.environ.get("REFINER_TOPIC_" + name.upper(), default)
            for name, default in OUT_TOPICS.items()
        },
    }


def load_maps(path: str | None, state_path: str | None = None) -> Maps:
    """시작 대응표(path) + 지난번에 배운 대응표(state_path). 시작 대응표가 우선이다."""
    maps = Maps(json.loads(Path(path).read_text(encoding="utf-8"))) if path else Maps()
    if state_path and Path(state_path).exists():
        maps.merge(Maps(json.loads(Path(state_path).read_text(encoding="utf-8"))))
    maps.changed = False
    maps.rates = RateBook.load(os.environ.get("RATES_PATH"))
    return maps


def save_maps(maps: Maps, state_path: str | None) -> None:
    """배운 것이 있으면 상태 파일에 저장한다 (임시 파일에 쓰고 바꿔 끼워 반쯤 쓴 파일을 막는다)."""
    if not state_path or not maps.changed:
        return
    p = Path(state_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(maps.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    maps.changed = False


def dry_run(input_path: str, maps_path: str | None, out_dir: str) -> None:
    maps = load_maps(maps_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    n_in = n_ignored = 0

    with ExitStack() as stack:
        files: dict[str, Any] = {}

        def write(name: str, obj: dict[str, Any]) -> None:
            if name not in files:
                fname = (
                    "refined.games.extras.jsonl" if name == "extras" else f"refined.{name}.jsonl"
                )
                files[name] = stack.enter_context(open(out / fname, "w", encoding="utf-8"))
            files[name].write(json.dumps(obj, ensure_ascii=False) + "\n")
            counts[name] = counts.get(name, 0) + 1

        with open(input_path, encoding="utf-8") as fin:
            for line in fin:
                if not line.strip():
                    continue
                n_in += 1
                res = route(json.loads(line), maps)
                if res["ignored"]:
                    n_ignored += 1
                for name, key, msg in res["out"]:
                    write(name, {"key": key, "value": msg})
                for u in res["unmatched"]:
                    write("unmatched", u)
                if res["extras"]:
                    write("extras", res["extras"])
    summary = ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "없음"
    log.info("dry-run 완료: 입력 %d (정제 규칙 없음 %d), 출력 %s", n_in, n_ignored, summary)
    (out / "id_map.learned.json").write_text(
        json.dumps(maps.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    log.info("대응표 %s → %s", maps.size(), out / "id_map.learned.json")


def run_kafka() -> None:  # pragma: no cover - 서버(kafka1~3)에서만 실행
    from confluent_kafka import Consumer, Producer

    t = topics()
    bootstrap = os.environ["KAFKA_BOOTSTRAP"]
    state_path = os.environ.get("ID_MAP_STATE_PATH")
    maps = load_maps(os.environ.get("ID_MAP_PATH"), state_path)
    if not (maps.itad or maps.steam or maps.alias):
        log.warning("대응표가 비어 있다: raw.igdb 를 먼저 받아야 가격·사양이 게임에 연결된다")

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": "refiner",
            "enable.auto.commit": False,  # 발행이 끝난 뒤에만 commit (at-least-once)
            "auto.offset.reset": "earliest",
        }
    )
    producer = Producer(
        {
            "bootstrap.servers": bootstrap,
            "acks": "all",
            "enable.idempotence": True,
            "delivery.timeout.ms": 300000,  # 짧은 장애는 기다렸다 보낸다 (Kafka 구축 문서 4장)
        }
    )
    consumer.subscribe(t["in"])
    log.info(
        "refiner start: %s → %s (대응표 %s)",
        ",".join(t["in"]),
        ",".join(t[n] for n in OUT_TOPICS),
        maps.size(),
    )
    counts: dict[str, int] = {}
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                log.error("consume error: %s", msg.error())
                continue
            try:
                res = route(json.loads(msg.value()), maps)
            except (ValueError, TypeError, KeyError) as e:  # 깨진 메시지는 멈추지 않고 unmatched 로
                res = {
                    "out": [],
                    "ignored": False,
                    "extras": {},
                    "unmatched": [
                        {
                            "reason": f"메시지 해석 실패: {e}",
                            "source": msg.topic(),
                            "key": msg.key().decode() if msg.key() else None,
                        }
                    ],
                }
            for name, key, value in res["out"]:
                producer.produce(t[name], key=key, value=json.dumps(value, ensure_ascii=False))
                counts[name] = counts.get(name, 0) + 1
            for u in res["unmatched"]:
                producer.produce(
                    t["unmatched"], key=str(u.get("key")), value=json.dumps(u, ensure_ascii=False)
                )
                counts["unmatched"] = counts.get("unmatched", 0) + 1
            producer.flush()
            save_maps(maps, state_path)  # commit 전에 저장: 재시작해도 배운 대응표가 남는다
            consumer.commit(msg)
            if res["out"] or res["unmatched"]:
                log.info("누계 %s", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    finally:
        consumer.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="refiner")
    ap.add_argument("--dry-run", action="store_true", help="Kafka 없이 파일로만 실행")
    ap.add_argument("--input", help="raw 봉투 JSON Lines 파일")
    ap.add_argument("--id-map", help="매칭 대응표 JSON 파일")
    ap.add_argument("--out", default="out", help="dry-run 출력 폴더")
    a = ap.parse_args(argv)
    if a.dry_run:
        if not a.input:
            ap.error("--dry-run 에는 --input 이 필요합니다")
        dry_run(a.input, a.id_map, a.out)
    else:
        run_kafka()


if __name__ == "__main__":
    main()
