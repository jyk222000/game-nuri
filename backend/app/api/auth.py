"""구글 로그인(#1)·세션 갱신·로그아웃(#2). 얇게 유지하고 일은 services/auth.py가 한다.

- GET  /api/auth/google/login     구글로 리다이렉트 + state 쿠키
- GET  /api/auth/google/callback  세션 쿠키 발급 후 `/`로 이동 (본문 없음)
- POST /api/auth/refresh          세션 유효 기간을 다시 센다 (로그인 필요)
- POST /api/auth/logout           세션 삭제 (로그인 필요)
세션 id·코드·state 값은 로그에 남기지 않는다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.keys import SESSION_COOKIE_NAME
from app.db.session import get_write_db
from app.services import auth

router = APIRouter(prefix="/api/auth")

User = Annotated[CurrentUser, Depends(get_current_user)]
Db = Annotated[Session, Depends(get_write_db)]  # 로그인 때 users에 쓴다 → Primary

HOME = "/"


@router.get("/google/login")
def google_login() -> RedirectResponse:
    start = auth.start_login()
    response = RedirectResponse(start.url, status_code=302)
    response.set_cookie(auth.STATE_COOKIE_NAME, start.state_cookie, **auth.state_cookie_options())
    return response


@router.get("/google/callback")
def google_callback(
    request: Request, db: Db, code: str | None = None, state: str | None = None
) -> RedirectResponse:
    result = auth.finish_login(db, code, state, request.cookies.get(auth.STATE_COOKIE_NAME))
    response = RedirectResponse(HOME, status_code=302)
    response.set_cookie(SESSION_COOKIE_NAME, result.session_id, **auth.session_cookie_options())
    response.delete_cookie(auth.STATE_COOKIE_NAME, path="/api/auth")  # 임시 쿠키는 바로 지운다
    return response


@router.post("/refresh")
def refresh(request: Request, response: Response, user: User) -> dict[str, bool]:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:  # 개발용 가짜 사용자(쿠키 없음)는 갱신할 세션이 없다
        auth.refresh_session(session_id)
        # 서버 세션과 브라우저 쿠키의 유효 기간을 같이 연장한다
        response.set_cookie(SESSION_COOKIE_NAME, session_id, **auth.session_cookie_options())
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, user: User) -> dict[str, bool]:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        auth.delete_session(session_id)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}
