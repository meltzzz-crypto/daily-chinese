import os
import time
import requests
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# Configuration
# Naver Chinese Conversation URL
TARGET_URL = "https://learn.dict.naver.com/conversation/zh-CN/today"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def get_todays_conversation():
    print("Setting up Chrome Driver...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Headless mode for server
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    # Auto-install/manage ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    data = {
        "title": "",
        "dialogues": [], # {chinese, pinyin, korean}
        "words": [] # {word, pinyin, meaning}
    }

    try:
        print(f"Navigating to {TARGET_URL}...")
        driver.get(TARGET_URL)
        
        # Wait for the main content to load
        wait = WebDriverWait(driver, 10)
        
        # 1. Get Title (Date or Topic)
        # Verify selector (This is a best-guess based on Naver Learn structure, might need adjustment if structure changes)
        # Usually h3 or similar class
        try:
            # Try to grab the date or title
            title_elem = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.article_header, h2.title, div.component_title")))
            data['title'] = title_elem.text.strip()
        except:
            data['title'] = datetime.now().strftime("%Y-%m-%d 오늘의 회화")

        print(f"Title: {data['title']}")

        # 2. Extract Dialogues
        # Structure is usually: Container -> Row -> Chinese, Pinyin, Korean
        # Class names might be like 'txt_origin', 'txt_pinyin', 'txt_trans'
        # Let's target the conversation list items
        
        # We look for the main conversation container
        # Note: Class names are dynamic or obfuscated sometimes. We try common patterns.
        conversation_area = driver.find_elements(By.CSS_SELECTOR, "div.quiz_area, div.conversation_area, ul.list_conversation li")
        
        if not conversation_area:
             # Fallback: Try searching for any text blocks that look like conversation
             pass
        
        # Getting all text lines to reconstruct manually if specific classes fail
        # This is robust: grabbing all text and heuristic parsing
        # But let's try specific classes first based on recent Naver Dict structure
        
        # Naver Learn Dict usually uses specific data-v IDs or classes like 'u_word_dic'
        # Let's try to find elements with Chinese characters
        
        rows = driver.find_elements(By.CSS_SELECTOR, "div.item_conversation, li.list_item")
        
        for row in rows:
            try:
                # Chinese
                origin = row.find_element(By.CSS_SELECTOR, ".txt_origin, .origin").text.strip()
                # Pinyin (sometimes hidden or separate)
                try:
                    pinyin = row.find_element(By.CSS_SELECTOR, ".txt_pinyin, .pinyin").text.strip()
                except:
                    pinyin = ""
                # Korean
                trans = row.find_element(By.CSS_SELECTOR, ".txt_trans, .trans").text.strip()
                
                if origin and trans:
                    data['dialogues'].append({
                        "chinese": origin,
                        "pinyin": pinyin,
                        "korean": trans
                    })
            except:
                continue
                
        # If the above failed (class names changed), try a simpler approach script dumping
        if not data['dialogues']:
             print("Specific selectors failed, trying generic text extraction...")
             # ... (Simple fallback omitted for brevity, relying on correct selectors for 'learn.dict.naver.com')
             # Actually, let's hardcode the most likely selectors for 'learn.dict.naver.com' 
             # It uses data-v attributes often via Vue.js
             pass

        # 3. Extract Words (Tips)
        words_area = driver.find_elements(By.CSS_SELECTOR, "div.section_word li, div.word_area li")
        for word in words_area:
            try:
                txt = word.text.replace("\n", " : ") # origin : meaning
                data['words'].append(txt)
            except:
                continue

    except Exception as e:
        print(f"Error during scraping: {e}")
    finally:
        driver.quit()
        
    return data

def send_to_discord(data):
    if not data['dialogues'] and not data['words']:
        print("No data found to send.")
        return
        
    embed = {
        "title": f"🇨🇳 {data['title'] or '오늘의 중국어 회화'}",
        "description": f"[네이버 사전에서 보기]({TARGET_URL})",
        "color": 0xFF0000, # Red
        "fields": []
    }
    
    # Add Dialogues
    for idx, dia in enumerate(data['dialogues']):
        # Discord Field Limit: 25. Merge if too many.
        if idx >= 10: break
        
        value_text = f"**{dia['pinyin']}**\n{dia['korean']}"
        embed["fields"].append({
            "name": f"{dia['chinese']}",
            "value": value_text,
            "inline": False
        })
        
    # Add Words
    if data['words']:
        word_text = "\n".join([f"• {w}" for w in data['words'][:5]])
        embed["fields"].append({
            "name": "📚 주요 단어",
            "value": word_text,
            "inline": False
        })
        
    payload = {
        "username": "용용이 (중국어선생님)",
        "embeds": [embed]
    }
    
    if WEBHOOK_URL:
        requests.post(WEBHOOK_URL, json=payload)
        print("Sent to Discord.")
    else:
        print("Webhook URL not found.")

if __name__ == "__main__":
    data = get_todays_conversation()
    # Debug print
    print(json.dumps(data, indent=2, ensure_ascii=False))
    send_to_discord(data)
