# shared — 공통 패키지

모든 Python 서비스가 `pip install -e shared`로 쓰는 패키지. **여기를 바꾸면 모든 파트에 영향**이 간다.
- 고치기 전에 사용자에게 알리고, shared만 담은 별도 PR로 올린다 (루트 CLAUDE.md 4-2).
- `messages.py`는 `docs/contracts/`와 항상 같아야 한다. 둘 중 하나만 바꾸지 않는다.
- 여기에는 설정·로깅·메시지 모델·시간 유틸처럼 **두 파트 이상이 쓰는 것만** 둔다.
