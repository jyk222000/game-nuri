import pytest
from refiner.router import Maps, route
from refiner.rules.danawa_match import TitleMatcher, exclude_reason, norm


@pytest.mark.parametrize(
    ("title", "reason"),
    [
        ("Thrustmaster eSWAP X 2 PRO 컨트롤러", "비게임 상품"),
        ("스위치2 엘든링 빛 바랜자 에디션/한글판/케이스포함 중고", "비게임 상품"),
        ("Microsoft XBOX One X 1TB 게임 번들", "본체 번들"),
        ("PS5 슬림 본체 + 갓 오브 워", "본체 번들"),
        ("[해외] PS5 엘든링 ELDEN RING NIGHTREIGN", "해외판"),
        ("프롬 소프트웨어 엘든 링 확장팩: 황금 나무의 그림자 한글판", "DLC·확장팩"),
        ("사이버펑크 2077 얼티밋 에디션 본편+팬텀 리버티 / PC 스팀코드", "에디션 (본편 아님)"),
        ("캡콤 몬스터 헌터 월드 아이스본 마스터 에디션 PC", "에디션 (본편 아님)"),
        ("프롬 소프트웨어 엘든 링 한글판", None),
        ("SIEK [중고]중고 PS5 갓오브워 라그나로크 한글판", None),
    ],
)
def test_exclude_reason(title, reason):
    assert exclude_reason(title) == reason


def test_norm_roman_and_symbols():
    assert norm("The Witcher III: Wild Hunt") == "thewitcher3wildhunt"
    assert norm("바이오하자드 RE:4") == "바이오하자드re4"


M = TitleMatcher(
    {
        "엘든 링": 1,
        "레드 데드 리뎀션 2": 2,
        "하데스": 3,
        "God of War": 4,
        "God of War II": 5,
        "갓 오브 워 라그나로크": 6,
        "갓 오브 워": 4,
        "Control": 7,
        "RE4": 8,
        "몬헌": 9,
    }
)


@pytest.mark.parametrize(
    ("title", "gid"),
    [
        ("프롬 소프트웨어 엘든링 한글판", 1),
        ("[매장정품] 플레이스테이션 [PS4] 레드 데드 리뎀션 2 2316207", 2),  # 뒤 상품 코드
        ("하데스 플레이스테이션 5", 3),
        ("하데스2 일본발매", None),  # 붙은 숫자 = 후속작
        ("하데스 2 PS5", None),  # 떨어진 1~2자리 = 후속작
        ("God of War 2018", 4),  # 떨어진 연도
        ("God of War 2", 5),  # 로마 숫자 별칭
        ("산타모니카 갓 오브 워: 라그나로크 한글판", 6),  # 더 긴 별칭이 이긴다
        ("플레이스테이션 PS4 갓 오브 워 PS Hits", 4),
        ("xbox controller", None),  # 영문 별칭은 단어 경계
        ("RE4 리메이크", None),  # 영문 5글자 미만 약어는 안 씀
        ("몬헌 월드", 9),  # 한글 2글자 별칭은 씀
    ],
)
def test_title_matcher(title, gid):
    assert M.match(title)[0] == gid


def test_same_length_different_games_is_ambiguous():
    m = TitleMatcher({"하데스": 1, "디아블": 2})
    gid, why = m.match("하데스 디아블 합본")
    assert gid is None and "확인 필요" in why


def test_router_console_uses_filters_and_matcher():
    maps = Maps({"alias": {"엘든 링": 119133}})

    def env(title):
        return {
            "source": "danawa",
            "kind": "console_price",
            "collected_at": "2026-11-23T00:00:00Z",
            "payload": {
                "pcode": "1",
                "product_name": title,
                "platform_hint": "PS5",
                "lowest_price": 52000,
            },
        }

    ok = route(env("프롬 소프트웨어 엘든링 한글판"), maps)
    assert ok["out"][0][2]["payload"]["game_id"] == 119133
    # 같은 회차에 본편이 이미 있으면 에디션은 가격에 쓰지 않는다 (#93)
    assert route(env("엘든 링 GOTY 에디션"), maps)["unmatched"][0]["reason"] == "에디션 (본편 있음)"
    assert route(env("PS5 본체 엘든 링 번들"), maps)["unmatched"][0]["reason"] == "본체 번들"
