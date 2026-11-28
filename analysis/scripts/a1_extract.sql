-- A1 데이터 추출: PC 새 상품 가격 이력 (mariadb-re에서, 읽기 전용)
-- price_history는 "가격이 바뀐 때"만 쌓여 있다. 분석 대상 게임 1,000개(analysis/game_list/games_1000.csv)는 노트북에서 거른다.
-- 서비스(backend/app/services/timing.py)와 같은 기준으로 PC·새 상품(item_condition='new') 이력만 뽑는다.
-- mysql -u <읽기 계정> -p gamenuri -B --default-character-set=utf8mb4 < analysis/scripts/a1_extract.sql > analysis/data/a1_price_history.tsv
SELECT p.game_id, p.store, p.edition, p.price_krw, p.regular_krw, p.discount_pct, p.collected_at
FROM price_history p
WHERE p.platform = 'PC' AND p.item_condition = 'new'
ORDER BY p.game_id, p.collected_at;
