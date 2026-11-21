"""겜누리 분석 패키지.

계산(pandas) → 그래프(matplotlib, PNG) → 요약(JSON). 노트북은 이 모듈을 불러 쓴다.
- A: out/figures/<분석>/*.png + summary.json  → 프론트가 정적 파일로 보여 줌
- B: out/api/*.json                          → Backend가 API로 내려 줌
     (게임별 태그, 사양표 신뢰도, 구매 타이밍 규칙)
"""
