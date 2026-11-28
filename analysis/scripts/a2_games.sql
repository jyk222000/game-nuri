-- A2 데이터 추출 ① 게임 목록 (mariadb-re에서, 읽기 전용)
-- 한글 이름이 3글자 이상인 본편 게임 중 한국어 리뷰가 많은 순 150개. 노트북이 이 중 TOP_N개를 쓴다.
-- mysql -u <읽기 계정> -p gamenuri -B < analysis/scripts/a2_games.sql > analysis/data/a2_games.tsv
SELECT g.game_id, g.name, g.name_ko, g.release_date, g.game_type, g.is_online,
       s.review_count_ko,
       (SELECT GROUP_CONCAT(ge.name ORDER BY ge.name SEPARATOR '|')
          FROM game_genres gg JOIN genres ge USING (genre_id) WHERE gg.game_id = g.game_id) AS genres
FROM games g
JOIN game_review_stats s USING (game_id)
WHERE g.parent_game_id IS NULL
  AND g.game_type IN (0, 8, 9, 10)          -- 본편·리메이크·리마스터·확장 본편 (게임 선정 기준 H1과 같음)
  AND g.name_ko IS NOT NULL
  AND CHAR_LENGTH(g.name_ko) >= 3           -- 2글자 이하는 네이버 검색어가 모호하다
  AND s.review_count_ko IS NOT NULL
ORDER BY s.review_count_ko DESC
LIMIT 150;
