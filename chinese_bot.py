import os
import time
import requests
import json
import re
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
    print("브라우저 시작 중...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument("--window-size=1280,1600")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    data = {"title": "", "dialogues": [], "words": [], "debug_msg": ""}

    try:
        print(f"{TARGET_URL} 접속 시도...")
        driver.get(TARGET_URL)
        time.sleep(10)  # 로딩 시간을 10초로 대폭 늘림
        
        # 스크린샷 캡처 (디버깅용)
        driver.save_screenshot("debug_screenshot.png")
        data['debug_msg'] = f"접속 타이틀: {driver.title}\n현재 URL: {driver.current_url}"

        # JSON 데이터 추출 시도
        try:
            page_source = driver.page_source
            match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});', page_source, re.DOTALL)
            
            if match:
                json_data = json.loads(match.group(1))
                
                def find_key(obj, key):
                    if isinstance(obj, dict):
                        if key in obj: return obj[key]
                        for k, v in obj.items():
                            res = find_key(v, key)
                            if res: return res
                    elif isinstance(obj, list):
                        for v in obj:
                            res = find_key(v, key)
                            if res: return res
                    return None

                sentences = find_key(json_data, 'sentences') or find_key(json_data, 'sentenceList')
                if sentences:
                    for sent in sentences:
                        chn = sent.get('origin_text') or sent.get('orgnTxt') or sent.get('origin', '')
                        kor = sent.get('trans_text') or sent.get('transTxt') or sent.get('trans', '')
                        pin = sent.get('pinyin_text') or sent.get('pinyinTxt') or sent.get('pinyin', '')
                        
                        chn = re.sub(r'<[^>]+>', '', chn).strip()
                        kor = re.sub(r'<[^>]+>', '', kor).strip()
                        pin = re.sub(r'<[^>]+>', '', pin).strip()

                        if chn and kor:
                            data['dialogues'].append({"chinese": chn, "pinyin": pin, "korean": kor})

                words = find_key(json_data, 'words') or find_key(json_data, 'wordList')
                if words:
                     for w in words:
                         e = w.get('entry_name') or w.get('entryName') or w.get('origin', '')
                         m = w.get('mean_text') or w.get('meanTxt') or w.get('trans', '')
                         if e: data['words'].append(f"{e} : {m}")

                if data['dialogues']: data['title'] = f"{datetime.now().strftime('%Y-%m-%d')} 오늘의 회화"
        except Exception as e:
            print(f"추출 오류: {e}")

    except Exception as e:
        print(f"브라우저 오류: {e}")
    finally:
        driver.quit()
    return data

def send_to_discord(data):
    if not WEBHOOK_URL: return
    files = {}
    if os.path.exists("debug_screenshot.png"):
        files = {"file": ("screenshot.png", open("debug_screenshot.png", "rb"))}

    if not data['dialogues']:
        payload = {"username": "용용이 (디버그)", "content": f"⚠️ 데이터를 못 찾았어요.\n{data['debug_msg']}"}
        requests.post(WEBHOOK_URL, data=payload, files=files)
    else:
        embed = {
            "title": f"🇨🇳 {data['title']}",
            "color": 0xFF0000,
            "fields": []
        }
        for dia in data['dialogues'][:10]:
            val = f"{dia['pinyin']}\n{dia['korean']}" if dia['pinyin'] else dia['korean']
            embed["fields"].append({"name": dia['chinese'], "value": val, "inline": False})
            
        if data['words']:
            embed["fields"].append({"name": "📚 주요 단어", "value": "\n".join([f"• {w}" for w in data['words'][:5]])})
            
        requests.post(WEBHOOK_URL, data={"username": "용용이", "payload_json": json.dumps({"embeds": [embed]})}, files=files)

if __name__ == "__main__":
    send_to_discord(get_todays_conversation())
