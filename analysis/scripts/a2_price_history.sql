-- A2 데이터 추출 ② PC 새 상품 가격 이력 (mariadb-re에서, 읽기 전용)
-- ①(a2_games.sql)과 같은 150개 게임만. price_history는 "가격이 바뀐 때"만 쌓여 있다.
-- mysql -u <읽기 계정> -p gamenuri -B < analysis/scripts/a2_price_history.sql > analysis/data/a2_price_history.tsv
SELECT p.game_id, p.store, p.edition, p.discount_pct, p.price_krw, p.regular_krw, p.collected_at
FROM price_history p
JOIN (
  SELECT g.game_id
  FROM games g
  JOIN game_review_stats s USING (game_id)
  WHERE g.parent_game_id IS NULL
    AND g.game_type IN (0, 8, 9, 10)
    AND g.name_ko IS NOT NULL
    AND CHAR_LENGTH(g.name_ko) >= 3
    AND s.review_count_ko IS NOT NULL
  ORDER BY s.review_count_ko DESC
  LIMIT 150
) t USING (game_id)
WHERE p.platform = 'PC' AND p.item_condition = 'new'
ORDER BY p.game_id, p.collected_at;
