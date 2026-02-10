import os
import time
import requests
import json
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ===== 설정 =====
# 핵심: "/conversation/zh-CN/today" 가 아니라, "/conversation" 이 진짜 주소.
# 중국어 페이지는 AngularJS가 해시(#) 뒤의 경로를 처리해서 보여줌.
BASE_URL = "https://learn.dict.naver.com/conversation"
CHINESE_HASH = "#/cndic/today"
FULL_URL = f"{BASE_URL}{CHINESE_HASH}"

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def get_todays_conversation():
    """네이버 오늘의 회화(중국어) 데이터를 가져옵니다."""
    print("=" * 50)
    print("네이버 중국어 오늘의 회화 봇 시작")
    print("=" * 50)

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    chrome_options.add_argument("--window-size=1280,1600")
    # 언어 설정을 한국어로
    chrome_options.add_argument("--lang=ko-KR")
    chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'ko,ko-KR'})

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    data = {"title": "", "dialogues": [], "words": [], "debug_info": ""}

    try:
        # ===== 1단계: 기본 URL로 접속 (이게 핵심!) =====
        print(f"[1단계] 기본 URL 접속: {BASE_URL}")
        driver.get(BASE_URL)
        time.sleep(3)
        print(f"  → 페이지 타이틀: {driver.title}")
        print(f"  → 현재 URL: {driver.current_url}")

        # ===== 2단계: 해시를 변경해서 중국어 페이지로 이동 =====
        print(f"[2단계] 중국어 페이지로 해시 변경: {CHINESE_HASH}")
        driver.execute_script(f"window.location.hash = '/cndic/today';")
        time.sleep(8)  # AngularJS 라우팅 + AJAX 데이터 로딩 대기
        print(f"  → 현재 URL: {driver.current_url}")

        # ===== 3단계: 스크린샷 저장 =====
        driver.save_screenshot("debug_screenshot.png")
        print("[3단계] 스크린샷 저장 완료")

        # 현재 페이지 상태 확인
        page_title = driver.title
        current_url = driver.current_url
        data['debug_info'] = f"타이틀: {page_title}\nURL: {current_url}"

        # 404 페이지인지 확인
        page_source = driver.page_source
        if "Please check again" in page_source or "요청하신 페이지를 찾을 수 없습니다" in page_source:
            print("⚠️ 404 페이지 감지! 서비스가 종료되었을 수 있습니다.")
            data['debug_info'] += "\n⚠️ 404 페이지 감지됨"
            return data

        # ===== 4단계: 데이터 추출 =====
        print("[4단계] 데이터 추출 시도...")

        # 방법 A: 실제 렌더링된 HTML에서 회화 내용 추출
        # AngularJS가 렌더링한 후의 DOM에서 찾기
        try:
            # content 영역이 보일 때까지 대기
            WebDriverWait(driver, 10).until(
                lambda d: d.find_element(By.ID, "content").get_attribute("style") != "visibility: hidden;"
            )
            print("  → content 영역 visible 확인")
        except:
            print("  → content 영역 대기 타임아웃 (계속 진행)")

        # 회화 문장 찾기 - 여러 선택자 시도
        selectors_for_origin = [
            ".txt_origin",           # 원문 (중국어)
            ".origin_txt",           # 다른 패턴
            "[class*='origin']",     # origin 포함 클래스
            ".sentence_wrap .origin",
            ".reading_area .origin",
        ]
        
        selectors_for_trans = [
            ".txt_trans",            # 번역 (한국어)
            ".trans_txt",            # 다른 패턴
            "[class*='trans']",      # trans 포함 클래스
            ".sentence_wrap .trans",
            ".reading_area .trans",
        ]

        origins = []
        trans = []

        for sel in selectors_for_origin:
            origins = driver.find_elements(By.CSS_SELECTOR, sel)
            if origins:
                print(f"  → 원문 발견! 선택자: '{sel}', 개수: {len(origins)}")
                break

        for sel in selectors_for_trans:
            trans = driver.find_elements(By.CSS_SELECTOR, sel)
            if trans:
                print(f"  → 번역 발견! 선택자: '{sel}', 개수: {len(trans)}")
                break

        # 병음 찾기
        pinyin_elements = driver.find_elements(By.CSS_SELECTOR, ".pinyin, .txt_pinyin, [class*='pinyin']")
        print(f"  → 병음 개수: {len(pinyin_elements)}")

        # 대화 쌍 만들기
        min_count = min(len(origins), len(trans))
        for i in range(min_count):
            chn = origins[i].text.strip()
            kor = trans[i].text.strip()
            pin = pinyin_elements[i].text.strip() if i < len(pinyin_elements) else ""
            
            if chn and kor:
                data['dialogues'].append({
                    "chinese": chn,
                    "korean": kor,
                    "pinyin": pin
                })

        # 방법 B: 만약 위에서 못 찾았으면 전체 conversation_wrap 에서 텍스트 추출
        if not data['dialogues']:
            print("  → 선택자로 못 찾음. conversation_wrap 에서 통째로 시도...")
            conv_wraps = driver.find_elements(By.CSS_SELECTOR, ".conversation_wrap, .conv_area, .reading_area, #content")
            for wrap in conv_wraps:
                text = wrap.text.strip()
                if text and len(text) > 10:
                    print(f"  → conv_wrap 텍스트 발견 (길이: {len(text)})")
                    data['debug_info'] += f"\n\n[conv_wrap 텍스트]\n{text[:500]}"
                    break

        # 단어 찾기
        word_elements = driver.find_elements(By.CSS_SELECTOR, ".word_area li, .section_word li, [class*='word'] li")
        for w in word_elements:
            text = w.text.strip().replace("\n", " : ")
            if text:
                data['words'].append(text)

        if data['dialogues']:
            data['title'] = f"{datetime.now().strftime('%Y-%m-%d')} 오늘의 중국어 회화"
            print(f"\n✅ 성공! {len(data['dialogues'])}개 문장 추출")
        else:
            print(f"\n❌ 데이터를 찾지 못했습니다.")
            # HTML 소스 일부를 디버그 정보에 추가
            body_text = driver.find_element(By.TAG_NAME, "body").text[:800]
            data['debug_info'] += f"\n\n[페이지 본문 텍스트]\n{body_text}"

    except Exception as e:
        print(f"오류 발생: {e}")
        data['debug_info'] += f"\n오류: {e}"
        try:
            driver.save_screenshot("debug_screenshot.png")
        except:
            pass
    finally:
        driver.quit()

    return data


def send_to_discord(data):
    """데이터를 디스코드로 전송합니다."""
    if not WEBHOOK_URL:
        print("❌ DISCORD_WEBHOOK_URL 환경변수가 설정되지 않았습니다!")
        return

    # 스크린샷 파일 준비
    files = {}
    if os.path.exists("debug_screenshot.png"):
        files = {"file": ("screenshot.png", open("debug_screenshot.png", "rb"))}

    if not data['dialogues']:
        # 실패 시: 디버그 정보 + 스크린샷 전송
        msg = f"⚠️ 오늘의 중국어 회화 데이터를 가져오지 못했습니다.\n\n{data['debug_info']}"
        # Discord 메시지 길이 제한 (2000자)
        if len(msg) > 1900:
            msg = msg[:1900] + "\n...(생략)"
        
        requests.post(WEBHOOK_URL, data={
            "username": "용용이 (디버그)",
            "content": msg
        }, files=files)
        print("디버그 메시지 전송 완료")
        return

    # 성공 시: 회화 내용 전송
    embed = {
        "title": f"🇨🇳 {data['title']}",
        "description": f"[네이버 오늘의 회화 바로가기]({FULL_URL})",
        "color": 0xFF4444,
        "fields": [],
        "footer": {"text": "매일 자동 전송 | 네이버 사전"}
    }

    for dia in data['dialogues'][:10]:
        value_parts = []
        if dia.get('pinyin'):
            value_parts.append(f"🔤 {dia['pinyin']}")
        value_parts.append(f"🇰🇷 {dia['korean']}")
        
        embed["fields"].append({
            "name": f"🇨🇳 {dia['chinese']}",
            "value": "\n".join(value_parts),
            "inline": False
        })

    if data['words']:
        word_text = "\n".join([f"• {w}" for w in data['words'][:5]])
        embed["fields"].append({
            "name": "📚 주요 단어/표현",
            "value": word_text,
            "inline": False
        })

    payload = {
        "username": "용용이",
        "payload_json": json.dumps({"embeds": [embed]})
    }
    
    response = requests.post(WEBHOOK_URL, data=payload, files=files)
    print(f"전송 완료 (상태코드: {response.status_code})")


if __name__ == "__main__":
    data = get_todays_conversation()
    print("\n--- 추출된 데이터 ---")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("-------------------\n")
    send_to_discord(data)
