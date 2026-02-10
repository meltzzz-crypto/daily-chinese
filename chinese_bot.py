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
        time.sleep(5)  # 로딩 대기

        # 1. JSON 데이터 추출 시도 (가장 확실한 방법)
        print("숨겨진 JSON 데이터 찾는 중...")
        try:
            # Naver Learn Dict는 보통 __PRELOADED_STATE__ 또는 유사한 변수에 데이터를 담습니다.
            page_source = driver.page_source
            match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});', page_source)
            
            if match:
                print("JSON 데이터 발견! 파싱 시도...")
                json_str = match.group(1)
                json_data = json.loads(json_str)
                
                # 재귀적으로 키를 찾는 함수
                def find_key(obj, key):
                    if isinstance(obj, dict):
                        if key in obj: return obj[key]
                        for k, v in obj.items():
                            item = find_key(v, key)
                            if item: return item
                    elif isinstance(obj, list):
                        for v in obj:
                            item = find_key(v, key)
                            if item: return item
                    return None

                # 대화 내용 찾기
                sentences = find_key(json_data, 'sentences') or find_key(json_data, 'sentenceList')
                
                if sentences:
                    print(f"대화 문장 {len(sentences)}개 발견 (JSON)")
                    for sent in sentences:
                        chn = sent.get('origin_text') or sent.get('orgnTxt') or sent.get('txt_origin') or sent.get('origin', '')
                        kor = sent.get('trans_text') or sent.get('transTxt') or sent.get('txt_trans') or sent.get('trans', '')
                        pin = sent.get('pinyin_text') or sent.get('pinyinTxt') or sent.get('txt_pinyin') or sent.get('pinyin', '')
                        
                        # 태그 제거
                        chn = re.sub(r'<[^>]+>', '', chn).strip()
                        kor = re.sub(r'<[^>]+>', '', kor).strip()
                        pin = re.sub(r'<[^>]+>', '', pin).strip()

                        if chn and kor:
                            data['dialogues'].append({
                                "chinese": chn,
                                "pinyin": pin,
                                "korean": kor
                            })

                # 단어 찾기
                words = find_key(json_data, 'words') or find_key(json_data, 'wordList')
                if words:
                     print(f"단어 {len(words)}개 발견 (JSON)")
                     for w in words:
                         entry = w.get('entry_name') or w.get('entryName') or w.get('txt_origin') or w.get('origin', '')
                         mean = w.get('mean_text') or w.get('meanTxt') or w.get('txt_trans') or w.get('trans', '')
                         if entry:
                             data['words'].append(f"{entry} : {mean}")

                if data['dialogues']:
                    data['title'] = f"{datetime.now().strftime('%Y-%m-%d')} 오늘의 회화 (JSON)"
                    return data 
        except Exception as e:
            print(f"JSON 추출 실패: {e}")

        # 2. JSON 실패 시 HTML 태그로 찾기 (Fallback)
        print("JSON 실패, HTML 태그로 재시도...")
        origins = driver.find_elements(By.CSS_SELECTOR, "[class*='origin'], [class*='chn']")
        trans = driver.find_elements(By.CSS_SELECTOR, "[class*='trans'], [class*='kor']")
        
        min_len = min(len(origins), len(trans))
        for i in range(min_len):
            chn = origins[i].text.strip()
            kor = trans[i].text.strip()
            if chn and kor:
                data['dialogues'].append({"chinese": chn, "korean": kor, "pinyin": ""})

        words = driver.find_elements(By.CSS_SELECTOR, "div.section_word li, ul[class*='word'] li")
        for w in words:
            data['words'].append(w.text.replace("\n", " : "))

        data['title'] = f"{datetime.now().strftime('%Y-%m-%d')} 오늘의 회화 (HTML)"

    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        driver.quit()
        
    return data

def send_to_discord(data):
    if not WEBHOOK_URL:
        print("웹훅 주소가 없습니다!")
        return

    if not data['dialogues']:
        print("데이터 없음. 오류 메시지 전송.")
        requests.post(WEBHOOK_URL, json={
            "username": "용용이 (오류)",
            "content": "⚠️ 네이버 JSON 데이터도, HTML 태그도 모두 찾지 못했습니다. 네이버 보안이 강력해진 것 같습니다."
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
        val = f"{dia['pinyin']}\n{dia['korean']}" if dia.get('pinyin') else dia['korean']
        embed["fields"].append({
            "name": dia['chinese'],
            "value": val,
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
