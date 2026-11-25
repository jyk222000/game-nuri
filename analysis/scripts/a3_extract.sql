-- A3 데이터 추출 (mariadb-re에서, 읽기 전용)
-- mysql -u <읽기 계정> -p gamenuri -B < a3_extract.sql > analysis/data/a3_games.tsv
SELECT g.game_id, g.name, g.release_date, g.game_type, g.is_online, g.korean_supported, g.age_rating,
       g.rating, g.rating_count, g.aggregated_rating, g.aggregated_rating_count,
       s.review_count_ko, s.positive_pct_ko, s.review_label_ko,
       s.review_count_all, s.positive_pct_all, s.review_label_all,
       (SELECT GROUP_CONCAT(ge.name ORDER BY ge.name SEPARATOR '|')
          FROM game_genres gg JOIN genres ge USING (genre_id) WHERE gg.game_id = g.game_id) AS genres,
       (SELECT COUNT(*) FROM player_counts p WHERE p.game_id = g.game_id) AS pc_samples,
       (SELECT MAX(player_count) FROM player_counts p WHERE p.game_id = g.game_id) AS peak_players
FROM games g LEFT JOIN game_review_stats s USING (game_id)
WHERE g.parent_game_id IS NULL;
