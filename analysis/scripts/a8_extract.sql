-- A8 데이터 추출: 현재 가격 (PC + 콘솔, 새 상품) + 게임 정보 (mariadb-re에서, 읽기 전용)
-- 본편(variant_name 없음) 새 상품 가격만. PC는 ITAD, 콘솔은 다나와에서 온 값이다.
-- mysql -u <읽기 계정> -p gamenuri -B < analysis/scripts/a8_extract.sql > analysis/data/a8_prices.tsv
SELECT pc.game_id, g.name, g.name_ko, g.release_date, g.game_type, g.is_online,
       pc.store, pc.edition, pc.platform, pc.price_krw, pc.regular_krw, pc.discount_pct,
       pc.collected_at,
       s.review_count_ko,
       (SELECT GROUP_CONCAT(ge.name ORDER BY ge.name SEPARATOR '|')
          FROM game_genres gg JOIN genres ge USING (genre_id) WHERE gg.game_id = pc.game_id) AS genres
FROM prices_current pc
JOIN games g USING (game_id)
LEFT JOIN game_review_stats s USING (game_id)
WHERE pc.item_condition = 'new'
  AND pc.variant_name IS NULL
  AND pc.game_id IN (SELECT game_id FROM prices_current WHERE platform = 'PC' AND item_condition = 'new')
  AND pc.game_id IN (SELECT game_id FROM prices_current WHERE platform <> 'PC' AND item_condition = 'new')
ORDER BY pc.game_id, pc.platform, pc.price_krw;
