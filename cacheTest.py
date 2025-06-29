# context_cache_example.py
import datetime as dt
from vertexai import init                     # 정식 SDK
from vertexai.preview import caching          # <— 핵심!
from vertexai.generative_models import GenerativeModel, Part
import datetime
from zoneinfo import ZoneInfo

def convert_utc_string_to_kst(utc_string: str) -> str:
    """
    ISO 8601 형식의 UTC 시간 문자열을 한국 표준시(KST) 문자열로 변환합니다.

    Args:
        utc_string: 'YYYY-MM-DD HH:MM:SS.ffffff+00:00' 형식의 UTC 시간 문자열.

    Returns:
        YYYY-MM-DD HH:MM:SS (KST) 형식의 한국 표준시 문자열.
    """
    # 1. UTC 시간 문자열을 datetime 객체로 파싱합니다.
    # fromisoformat()은 ISO 8601 형식의 문자열을 자동으로 파싱하고
    # +00:00과 같은 타임존 정보를 포함하여 timezone-aware datetime 객체를 생성합니다.
    utc_dt = datetime.datetime.fromisoformat(utc_string)

    # 2. 한국 표준시(KST) 시간대를 정의합니다.
    kst_timezone = ZoneInfo("Asia/Seoul")

    # 3. UTC datetime 객체를 KST로 변환합니다.
    kst_dt = utc_dt.astimezone(kst_timezone)

    # 4. 원하는 형식으로 날짜와 시간을 포맷합니다.
    return kst_dt.strftime('%Y-%m-%d %H:%M:%S (KST)')

# ──────────────────────────────────────────────────────────────
# 1) 환경 설정 – API 키/프로젝트/리전
# ──────────────────────────────────────────────────────────────
API_KEY     = "비밀"                 # TODO: .env나 비밀관리 서비스로부터 읽어오기
PROJECT_ID  = "python-online-lesson-basic"                 # ex) "python-online-lesson-basic"
LOCATION    = "us-central1"      # 미국 멀티리전
MODEL_NAME  = "gemini-2.5-pro"   # 또는 "gemini-2.5-pro-latest"
CACHE_NAME  = "lesson_session_01"   # 캐시 표시 이름(display_name)

# Application-Default Credentials(ADC)나 API 키 방식 둘 중 하나를 사용
init(project=PROJECT_ID, location=LOCATION, api_key=API_KEY or None)

# ──────────────────────────────────────────────────────────────
# 2) “캐시가 이미 있는지” 확인하는 유틸 함수
# ──────────────────────────────────────────────────────────────
def get_or_create_cache(display_name: str, model_name: str):
    """동일 display_name 캐시가 있으면 재사용, 없으면 새로 만든다."""
    #found = caching.CachedContent.list(
    #    filter=f'display_name="{display_name}"'
    #)                              # 새 SDK에선 프로젝트·리전 자동 반영
    cache_list: list[caching.CachedContent] = caching.CachedContent.list()
    found = next((cc for cc in cache_list if cc.display_name == CACHE_NAME), None)
    if found:
        print(f"[hit] reuse cache: {found.__dict__}")
        return found            # 첫 번째 매칭 캐시 반환

    # 없으면 새로 생성 (텍스트 1줄이라도 contents 필요)
    seed_memory = """
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
작성자의 이름은 이윤선이고 친구의 이름은 이강원이다
    """
    new_cache = caching.CachedContent.create(
        display_name=display_name,
        model_name=model_name,
        contents=[Part.from_text(seed_memory)],
        ttl= "600s" #dt.timedelta(days=30)   # 기본 60분 → 30일로 연장
    )
    print(f"[miss] create cache: {new_cache.__dict__}")
    return new_cache

# ──────────────────────────────────────────────────────────────
# 3) 캐시 확보 후, 모델 호출
# ──────────────────────────────────────────────────────────────
cache = get_or_create_cache(CACHE_NAME, MODEL_NAME)
print(convert_utc_string_to_kst(str(cache.expire_time)))
#cache.update(ttl="600s")
updated_cache = caching.CachedContent.get(cached_content_name=cache.name)

print(convert_utc_string_to_kst(str(updated_cache.expire_time)))

quit()
model = GenerativeModel.from_cached_content(cached_content=cache)

# (방법 A) 단일 요청
resp = model.generate_content(
   "작성자의 이름과 , 친구의 이름을 말해봐"
)
print(resp.text)

# (방법 B) 다중 턴 채팅
# chat = model.start_chat(cached_content=cache.name)
# print(chat.send_message("안녕! 캐시가 잘 적용됐니?").text)
