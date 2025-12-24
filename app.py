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

# 1. 페이지 설정 (가장 먼저 실행되어야 함)
st.set_page_config(page_title="URL Multi-Checker", layout="wide")

# --- [로직] 각 플랫폼 검증 함수들 ---
def check_pinterest_status(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        pin_id = url.strip('/').split('/')[-1]
        if response.status_code == 200 and pin_id in response.url:
            if 'pinterestapp:pin' in response.text or 'og:title' in response.text:
                return "Active"
        return "Dead"
    except: return "Error"

def check_trenbe_status(url, driver):
    try:
        driver.get(url)
        time.sleep(4)
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
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if any(kw in body_text for kw in ['판매가 종료된', '품절된 상품', '상품이 존재하지 않습니다']): return "Expired"
        if any(kw in body_text for kw in ['장바구니', '바로구매']): return "Active"
        return "Expired"
    except: return "Error"

def check_11st_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        product_id = match.group() if match else ""
        driver.get(f"https://search.11st.co.kr/Search.tmall?kwd={product_id}")
        time.sleep(4)
        if "검색 결과가 없습니다" in driver.page_source: return "Expired"
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
        return "Active" if any(product_id in item.get_attribute('href') for item in items) else "Expired"
    except: return "Error"

def check_mustit_status(url, driver):
    try:
        driver.get(url)
        time.sleep(4)
        try: driver.switch_to.alert.accept()
        except: pass
        if "redirector" in driver.current_url or any(kw in driver.page_source for kw in ["판매종료", "존재하지"]): return "Expired"
        return "Active"
    except: return "Error"

# --- [Selenium 설정] 로그에 나타난 실제 경로 반영 ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # 로그(Apt dependencies)에 설치된 경로 강제 지정
    options.binary_location = "/usr/bin/chromium"
    service = Service("/usr/bin/chromedriver")
    
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except:
        # 로컬(맥/윈도우) 실행 시 자동 다운로드 사용
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

# --- [UI 메인] ---
st.title("📌 통합 URL 상태 확인 도구")

selected_platforms = st.sidebar.multiselect(
    "분석할 플랫폼을 선택하세요",
    ["pinterest.com", "trenbe.com", "mustit.co.kr", "11st.co.kr"],
    default=["trenbe.com"]
)

uploaded_file = st.file_uploader("분석할 CSV 파일을 업로드하세요", type=["csv"])

if uploaded_file is not None:
    try: df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
    except: df = pd.read_csv(uploaded_file, encoding='cp949')

    if st.button("분석 시작"):
        # D열(결과 기록열) 확보
        if len(df.columns) < 4: df["Result"] = ""
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        needs_browser = any(p in selected_platforms for p in ["trenbe.com", "mustit.co.kr", "11st.co.kr"])
        driver = get_driver() if needs_browser else None
        
        for idx in range(len(df)):
            url = str(df.iloc[idx, 2])          # C열 (index 2)
            platform_info = str(df.iloc[idx, 13]).lower() # N열 (index 13)
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
            progress_bar.progress((idx + 1) / len(df))
            status_text.text(f"진행 중: {idx+1}/{len(df)} | 결과: {result}")

        if driver: driver.quit()
        st.success("분석 완료!")
        st.dataframe(df.head(20))
        st.download_button("결과 파일 다운로드", df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "result.csv", "text/csv")
