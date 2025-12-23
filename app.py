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

# --- [플랫폼별 개별 로직 함수화] ---

def check_pinterest_status(url):
    headers = {"User-Agent": "Mozilla/5.0"}
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
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        product_id = match.group()
        driver.get(f"https://www.trenbe.com/search?keyword={product_id}")
        time.sleep(4.5)
        page_source = driver.page_source
        if any(kw in page_source for kw in ['결과가 없습니다', '검색결과가 없습니다']):
            return "Expired"
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        is_exact_match = any(product_id in (item.get_attribute('href') or "") for item in items)
        return "Active" if is_exact_match else "Expired"
    except: return "Error"

def check_11st_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        product_id = match.group()
        driver.get(f"https://search.11st.co.kr/Search.tmall?kwd={product_id}")
        time.sleep(4)
        if f"{product_id}의 검색 결과가 없습니다" in driver.page_source:
            return "Expired"
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
        is_exact_match = any(product_id in (item.get_attribute('href') or "") for item in items)
        return "Active" if is_exact_match else "Expired"
    except: return "Error"

def check_mustit_status(url, driver):
    try:
        driver.get(url)
        time.sleep(4)
        curr = driver.current_url
        if "redirector" in curr or "판매종료" in urllib.parse.unquote(curr):
            return "Expired"
        if any(kw in driver.page_source for kw in ["판매종료된 상품", "존재하지 않는 상품"]):
            return "Expired"
        return "Active"
    except: return "Error"

# --- [드라이버 설정] ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

# --- [UI 구성] ---
st.set_page_config(page_title="URL Multi-Checker Pro", layout="wide")
st.title("🔍 통합 상품 상태 확인 도구 (다중 선택)")

# 사이드바 설정
selected_platforms = st.sidebar.multiselect(
    "1. 분석할 플랫폼 선택 (다중 선택 가능)",
    ["pinterest.com", "trenbe.com", "mustit.co.kr", "11st.co.kr"],
    default=["pinterest.com"]
)
input_method = st.sidebar.radio("2. 입력 방식 선택", ["CSV 업로드", "구글 시트 URL"])

df = None
if input_method == "CSV 업로드":
    file = st.file_uploader("CSV 파일 선택", type=["csv"])
    if file:
        try: df = pd.read_csv(file, encoding='utf-8-sig')
        except: df = pd.read_csv(file, encoding='cp949')
else:
    gs_url = st.text_input("구글 시트 URL")
    if gs_url and "/d/" in gs_url:
        sid = gs_url.split("/d/")[1].split("/")[0]
        df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv")

# --- [실행 루프] ---
if df is not None and selected_platforms:
    if st.button("🚀 선택한 플랫폼 분석 시작"):
        progress = st.progress(0)
        status_label = st.empty()
        
        # 브라우저 필요 여부 확인
        needs_browser = any(p in selected_platforms for p in ["trenbe.com", "mustit.co.kr", "11st.co.kr"])
        driver = get_driver() if needs_browser else None
        
        total = len(df)
        for idx in range(total):
            url = str(df.iloc[idx, 2]) # C열
            raw_platform = str(df.iloc[idx, 13]).lower() # N열
            result = "Skipped"

            # 1. Pinterest (Requests)
            if "pinterest.com" in selected_platforms and "pinterest" in raw_platform:
                result = check_pinterest_status(url)
            
            # 2. Trenbe (Selenium ID Check)
            elif "trenbe.com" in selected_platforms and "trenbe" in raw_platform:
                result = check_trenbe_status(url, driver)
            
            # 3. 11st (Selenium ID Check)
            elif "11st.co.kr" in selected_platforms and ("11st" in raw_platform or "11번가" in raw_platform):
                result = check_11st_status(url, driver)
            
            # 4. Mustit (Selenium Redirect Check)
            elif "mustit.co.kr" in selected_platforms and "mustit" in raw_platform:
                result = check_mustit_status(url, driver)

            df.iloc[idx, 3] = result # D열 기록
            progress.progress((idx + 1) / total)
            status_label.text(f"[{idx+1}/{total}] {raw_platform} 확인 중... 결과: {result}")

        if driver: driver.quit()
        st.success("🎉 분석 완료!")
        st.dataframe(df)
        st.download_button("📥 결과 CSV 다운로드", df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "multi_result.csv", "text/csv")
