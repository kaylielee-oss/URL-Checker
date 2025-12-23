import streamlit as st
import pandas as pd
import time
import re
import io
import urllib.parse
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- [로직 1: pinterest.com] ---
def check_pinterest_status(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        pin_id = url.strip('/').split('/')[-1]
        if response.status_code == 200 and pin_id in response.url:
            if 'pinterestapp:pin' in response.text or 'og:title' in response.text:
                return "Active"
        return "Dead"
    except:
        return "Error"

# --- [로직 2: trenbe.com (정밀 ID 대조)] ---
def check_trenbe_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        product_id = match.group()
        
        search_url = f"https://www.trenbe.com/search?keyword={product_id}"
        driver.get(search_url)
        time.sleep(4) 

        page_source = driver.page_source
        no_result_keywords = ['검색 결과가 없습니다', '검색결과가 없습니다', '결과가 없습니다']
        if any(keyword in page_source for keyword in no_result_keywords):
            return "Expired"

        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        is_exact_match = any(product_id in (item.get_attribute('href') or "") for item in items)
        return "Active" if is_exact_match else "Expired"
    except:
        return "Error"

# --- [로직 3: 11st.co.kr (정밀 ID 대조)] ---
def check_11st_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        product_id = match.group()
        
        search_url = f"https://search.11st.co.kr/Search.tmall?kwd={product_id}"
        driver.get(search_url)
        time.sleep(4) 

        page_source = driver.page_source
        if f"{product_id}의 검색 결과가 없습니다" in page_source or "검색 결과가 없습니다" in page_source:
            return "Expired"

        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
        is_exact_match = any(product_id in (item.get_attribute('href') or "") for item in items)
        return "Active" if is_exact_match else "Expired"
    except:
        return "Error"

# --- [로직 4: mustit.co.kr (리다이렉트 & 문구 검증)] ---
def check_mustit_status(url, driver):
    try:
        driver.get(url)
        time.sleep(4) # 팝업이나 리다이렉트 대기 시간
        
        current_url = driver.current_url
        page_source = driver.page_source
        
        # 1. URL 리다이렉션 체크 (판매종료 시 특정 경로로 이동하는 경우)
        if "redirector" in current_url or "판매종료" in urllib.parse.unquote(current_url):
            return "Expired"
            
        # 2. 페이지 내 팝업 또는 안내 문구 체크
        expired_keywords = [
            "판매종료된 상품", 
            "판매가 종료된", 
            "존재하지 않는 상품", 
            "상품이 없습니다",
            "판매 종료된"
        ]
        
        if any(kw in page_source for kw in expired_keywords):
            return "Expired"
            
        return "Active"
    except:
        return "Error"

# --- [드라이버 설정] ---
def get_driver(platform_mode):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # 공통적으로 안정적인 User-Agent 설정
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

# --- [UI 구성] ---
st.set_page_config(page_title="URL Checker Pro", layout="wide")
st.title("🔍 통합 상품 상태 확인 도구 (전 플랫폼 정밀화)")

mode = st.sidebar.radio("1. 대상 플랫폼 선택", ["pinterest.com", "trenbe.com", "mustit.co.kr", "11st.co.kr"])
input_method = st.sidebar.radio("2. 입력 방식 선택", ["CSV 업로드", "구글 시트 URL"])

df = None
if input_method == "CSV 업로드":
    file = st.file_uploader("CSV 파일 선택", type=["csv"])
    if file:
        try: df = pd.read_csv(file, encoding='utf-8-sig')
        except: df = pd.read_csv(file, encoding='cp949')
else:
    url = st.text_input("구글 시트 URL")
    if url and "/d/" in url:
        sid = url.split("/d/")[1].split("/")[0]
        df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv")

if df is not None:
    if st.button("🚀 분석 시작"):
        progress = st.progress(0)
        status_label = st.empty()
        driver = get_driver(mode) if mode != "pinterest.com" else None
        
        for idx in range(len(df)):
            target_url = str(df.iloc[idx, 2])
            data_platform = str(df.iloc[idx, 13]).lower()
            result = "Skipped"

            try:
                if mode == "pinterest.com" and 'pinterest' in data_platform:
                    result = check_pinterest_status(target_url)
                elif mode == "trenbe.com" and 'trenbe' in data_platform:
                    result = check_trenbe_status(target_url, driver)
                elif mode == "11st.co.kr" and ('11st' in data_platform or '11번가' in data_platform):
                    result = check_11st_status(target_url, driver)
                elif mode == "mustit.co.kr" and 'mustit' in data_platform:
                    result = check_mustit_status(target_url, driver)
            except:
                result = "Error"

            df.iloc[idx, 3] = result
            progress.progress((idx + 1) / len(df))
            status_label.text(f"[{idx+1}/{len(df)}] {mode} 확인 중... 결과: {result}")

        if driver: driver.quit()
        st.success("🎉 분석 완료!")
        st.dataframe(df)
        st.download_button("📥 결과 CSV 다운로드", df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "check_result.csv", "text/csv")
