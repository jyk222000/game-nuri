# A3 평론 vs 유저 평가 괴리 (+ 유저 긍정률 예측)

담당: 이고은 · 데이터: 2026-11-25 mariadb-re (본편 게임 916개) · 코드: `analysis/scripts/a3_critic_vs_user.py`

- **평론** = IGDB `aggregated_rating` (평론 3개 이상 모인 게임 571개만)
- **유저** = Steam 한국어 리뷰 긍정 % (`game_review_stats.positive_pct_ko`)
- **괴리(gap)** = 유저 − 평론. +면 유저가 더 후하다.

## 찾은 것

| # | 결과 | 차트 |
|---|---|---|
| 1 | 평론과 한국 유저 평가는 **약하게만** 같이 움직인다 (순위상관 0.35) | `a3_1_scatter.png` |
| 2 | 아케이드·인디·플랫포머는 유저가 평론보다 6~8점 후하고, 전술·턴제 전략·슈터는 평론이 더 후하다 | `a3_2_genre_gap.png` |
| 3 | **2021년 이후 게임은 뒤집힌다**: 2020년까지는 유저가 평론보다 4~6점 높았는데, 2021~23년은 −3.7, 2024년 이후는 −8.6 | `a3_3_by_year.png` |
| 4 | 한국 유저는 전 세계 유저보다 평균 **3.7%p 박하다** (게임 70%에서 더 낮음). 한국어를 지원해도 차이가 줄지 않는다 (지원 −3.8, 미지원 −2.9) | `a3_4_korea_vs_global.png` |
| 5 | 평론 점수만으로 유저 긍정률을 예측하면 평균 9.5%p 틀린다 (R² 0.08). 출시 연도·리뷰 수·온라인·장르를 더하면 8.0%p (R² 0.33) | `a3_5_model_error.png` |
| 6 | 유저 긍정률에 영향이 큰 요소: 평론 점수 > 출시 연도 > 한국어 리뷰 수 > 온라인 > 인디 장르 | `a3_6_importance.png` |

숨은 명작 후보(유저가 훨씬 후함): The Plan, 7 Days to Die, Gal*Gun 2, House Flipper, Muse Dash
과대평가 후보(평론이 훨씬 후함): Starfield, Tekken 8, DNF Duel, Dawn of War III, Little Nightmares III
→ 위아래 10개씩은 스크립트를 돌리면 `gap_top.csv`로 나온다 (csv는 레포에 올리지 않음)

## 서비스에 쓰는 법
- 게임 상세에 "평론보다 유저 평가가 높은 게임(숨은 명작)" / "평론보다 유저 평가가 낮은 게임" 꼬리표
- 최신작은 평론 점수만 보고 사면 실망할 수 있다 → 구매 전 유저 리뷰(A4 불만 유형)를 같이 보여 준다

## 방법과 한계
- 예측 모델: 선형 회귀, Gradient Boosting. 5겹 교차검증 오차(MAE). 요소 중요도는 permutation importance (20회).
- 평론 점수가 없거나(170개) 평론 1~2개뿐인 게임은 뺐다.
- 상관·중요도는 "함께 나타난다"이지 원인은 아니다. 최신작이 낮은 것은 출시 직후 불만(버그·가격)이 리뷰에 몰리는 영향일 수 있다.
- `summary.json`에 모든 숫자가 있다 (화면·발표에서 그대로 쓴다).

## 다시 만들기
```bash
mysql -u <읽기 계정> -p gamenuri -B < analysis/scripts/a3_extract.sql > analysis/data/a3_games.tsv
python analysis/scripts/a3_critic_vs_user.py analysis/data/a3_games.tsv analysis/results/a3
```
