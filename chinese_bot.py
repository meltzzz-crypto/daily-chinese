import os
import time
import requests
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# 설정
TARGET_URL = "https://learn.dict.naver.com/conversation/zh-CN/today"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def get_todays_conversation():
    print("크롬 브라우저 시동 거는 중...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    data = {"title": "", "dialogues": [], "words": []}

    try:
        print(f"{TARGET_URL} 접속 중...")
        driver.get(TARGET_URL)
        time.sleep(5)  # 로딩 대기 (중요!)
        
        # 1. 태그로 찾기 (광범위 검색)
        print("대화 내용 찾는 중...")
        origins = driver.find_elements(By.CSS_SELECTOR, "[class*='origin'], [class*='chn']")
        trans = driver.find_elements(By.CSS_SELECTOR, "[class*='trans'], [class*='kor']")
        
        # 대화쌍 맞추기
        min_len = min(len(origins), len(trans))
        for i in range(min_len):
            chn = origins[i].text.strip()
            kor = trans[i].text.strip()
            if chn and kor:
                data['dialogues'].append({"chinese": chn, "korean": kor})

        # 2. 단어 찾기
        words = driver.find_elements(By.CSS_SELECTOR, "div.section_word li, ul[class*='word'] li")
        for w in words:
            data['words'].append(w.text.replace("\n", " : "))

        data['title'] = f"{datetime.now().strftime('%Y-%m-%d')} 오늘의 회화"

    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        driver.quit()
        
    return data

def send_to_discord(data):
    if not WEBHOOK_URL:
        print("웹훅 주소가 없습니다!")
        return

    # 실패 시 알림
    if not data['dialogues']:
        print("데이터 없음. 오류 메시지 전송.")
        requests.post(WEBHOOK_URL, json={
            "username": "용용이 (오류)",
            "content": "⚠️ 네이버 페이지에 들어갔는데 대화 내용을 못 찾았어요. (HTML 구조가 바뀐 것 같습니다.)"
        })
        return
        
    print(f"데이터 발견! {len(data['dialogues'])}문장 전송 중...")
    
    embed = {
        "title": f"🇨🇳 {data['title']}",
        "description": f"[네이버 사전 바로가기]({TARGET_URL})",
        "color": 0xFF0000,
        "fields": []
    }
    
    for dia in data['dialogues'][:10]:
        embed["fields"].append({
            "name": dia['chinese'],
            "value": dia['korean'],
            "inline": False
        })
        
    if data['words']:
        embed["fields"].append({
            "name": "📚 주요 단어",
            "value": "\n".join([f"• {w}" for w in data['words'][:5]]),
            "inline": False
        })
        
    requests.post(WEBHOOK_URL, json={"username": "용용이", "embeds": [embed]})
    print("전송 완료")

if __name__ == "__main__":
    data = get_todays_conversation()
    print(json.dumps(data, indent=2, ensure_ascii=False))
    send_to_discord(data)

