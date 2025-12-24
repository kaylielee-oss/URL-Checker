import streamlit as st
import pandas as pd
import requests
import time
import re
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- [로직 1] 핀터레스트 검증 ---
def check_pinterest_status(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        pin_id = url.strip('/').split('/')[-1]
        if response.status_code == 200 and pin_id in response.url:
            if 'pinterestapp:pin' in response.text or 'og:title' in response.text:
                return "Active"
        return "Dead"
    except:
        return "Error"

# --- [로직 2] 트렌비 검증 ---
def check_trenbe_status(url, driver):
    try:
        driver.get(url)
        time.sleep(4)
        page_source = driver.page_source
        
        # JSON-LD 분석
        scripts = driver.find_elements(By.XPATH, "//script[@type='application/ld+json']")
        for script in scripts:
            try:
                data = json.loads(script.get_attribute('innerHTML'))
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get('@type') == 'Product' or 'offers' in item:
                        availability = item.get('offers', {}).get('availability', '')
                        if 'InStock' in availability: return "Active"
                        elif 'OutOfStock' in availability: return "Expired"
            except: continue

        # 텍스트 분석
        body_text = driver.find_element(By.TAG_NAME, "body").text
        expired_keywords = ['판매가 종료된', '품절된 상품', '상품이 존재하지 않습니다', '정상적인 접근이 아닙니다']
        if any(kw in body_text for kw in expired_keywords): return "Expired"
        
        active_keywords = ['장바구니', '바로구매', 'BUY NOW']
        if any(kw in body_text for kw in active_keywords): return "Active"
        return "Expired"
    except:
        return "Error"

# --- [로직 3] 11번가 검증 ---
def check_11st_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        product_id = match.group()
        search_url = f"https://search.11st.co.kr/Search.tmall?kwd={product_id}"
        driver.get(search_url)
        time.sleep(4)
        page_source = driver.page_source
        if "검색 결과가 없습니다" in page_source: return "Expired"
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
        is_exact_match = any(product_id in item.get_attribute('href') for item in items)
        return "Active" if is_exact_match else "Expired"
    except: return "Error"

# --- [로직 4] 머스트잇 검증 ---
def check_mustit_status(url, driver):
    try:
        driver.get(url)
        time.sleep(4)
        try:
            alert = driver.switch_to.alert
            alert.accept()
        except: pass
        if "redirector" in driver.current_url or any(kw in driver.page_source for kw in ["판매종료", "존재하지"]):
            return "Expired"
        return "Active"
    except: return "Error"

# --- [핵심 수정] Selenium 설정 (Streamlit Cloud 환경 최적화) ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Streamlit Cloud 리눅스 환경의 경로 지정
    options.binary_location = "/usr/bin/chromium"
    
    # 드라이버 실행
    service = Service("/usr/bin/chromedriver")
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except:
        # 로컬 환경(윈도우/맥) 대비용
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

# --- [UI 실행부] ---
st.set_page_config(page_title="URL Multi-Checker", layout="wide")
st.title("📌 통합 URL 상태 확인 도구")

selected_platforms = st.sidebar.multiselect(
    "분석할 플랫폼을 선택하세요",
    ["pinterest.com", "trenbe.com", "mustit.co.kr", "11st.co.kr"],
    default=["trenbe.com"]
)

uploaded_file = st.file_uploader("분석할 CSV 파일을 업로드하세요", type=["csv"])

if uploaded_file is not None:
    # 인코딩 문제 방지를 위해 utf-8-sig 또는 cp949 시도
    try:
        df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
    except:
        df = pd.read_csv(uploaded_file, encoding='cp949')

    if st.button("분석 시작"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        needs_browser = any(p in selected_platforms for p in ["trenbe.com", "mustit.co.kr", "11st.co.kr"])
        driver = get_driver() if needs_browser else None
        
        # D열(index 3)이 없는 경우 생성
        if len(df.columns) < 4:
            df["Result"] = ""
            
        for idx in range(len(df)):
            try:
                url = str(df.iloc[idx, 2])          # C열
                platform_info = str(df.iloc[idx, 13]).lower() # N열
                result = "Skipped"
                
                if "trenbe.com" in selected_platforms and 'trenbe' in platform_info:
                    result = check_trenbe_status(url, driver)
                elif "pinterest.com" in selected_platforms and 'pinterest' in platform_info:
                    result = check_pinterest_status(url)
                elif "11st.co.kr" in selected_platforms and '11st' in platform_info:
                    result = check_11st_status(url, driver)
                elif "mustit.co.kr" in selected_platforms and 'mustit' in platform_info:
                    result = check_mustit_status(url, driver)
                
                df.iloc[idx, 3] = result 
            except Exception as e:
                df.iloc[idx, 3] = f"Error: {str(e)}"
                
            progress_bar.progress((idx + 1) / len(df))
            status_text
