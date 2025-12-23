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
    except: return "Error"

# --- [로직 2: trenbe.com (검색창 검색 기반 - 신규 로직)] ---
def check_trenbe_status(url, driver):
    try:
        # 1. URL에서 숫자(상품번호) 추출
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        product_id = match.group()
        
        # 2. 트렌비 검색 URL 생성 및 접속
        search_url = f"https://www.trenbe.com/search?keyword={product_id}"
        driver.get(search_url)
        time.sleep(5) # 검색 결과 로딩 대기
        
        # 3. 결과 판단
        page_source = driver.page_source
        
        # '검색 결과가 없습니다' 문구가 보이면 즉시 Expired
        no_result_text = ["검색 결과가 없습니다", "검색결과가 없습니다", "결과가 없습니다"]
        if any(kw in page_source for kw in no_result_text):
            return "Expired"
            
        # 4. 정밀 대조: 검색된 상품 리스트의 링크 중 내 product_id가 포함된 링크가 있는지 확인
        # (추천 상품만 뜨는 경우를 방지)
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        is_exact_match = any(product_id in (item.get_attribute('href') or "") for item in items)
        
        return "Active" if is_exact_match else "Expired"
    except: return "Error"

# --- [로직 3: 11st.co.kr (검색창 검색 기반)] ---
def check_11st_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        product_id = match.group()
        
        # 11번가 검색 URL 접속
        search_url = f"https://search.11st.co.kr/Search.tmall?kwd={product_id}"
        driver.get(search_url)
        time.sleep(4)
        
        page_source = driver.page_source
        if "검색 결과가 없습니다" in page_source:
            return "Expired"
            
        # 실제 검색 리스트에 해당 ID 상품이 있는지 확인
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
        is_exact_match = any(product_id in (item.get_attribute('href') or "") for item in items)
        
        return "Active" if is_exact_match else "Expired"
    except: return "Error"

# --- [로직 4: mustit.co.kr (알림창 및 리다이렉트)] ---
def check_mustit_status(url, driver):
    try:
        driver.get(url)
        time.sleep(5)
        # 알림창 처리
        try:
            alert = driver.switch_to.alert
            if any(kw in alert.text for kw in ["삭제", "판매종료", "존재하지 않는"]):
                alert.accept()
                return "Expired"
            alert.accept()
        except: pass
        
        curr = driver.current_url
        if "redirector" in curr or "etc/error" in curr: return "Expired"
        if any(kw in driver.page_source for kw in ["관리자에 의해 삭제", "판매종료된 상품"]): return "Expired"
        return "Active"
    except: return "Error"

# --- [드라이버 설정] ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    options.binary_location = "/usr/bin/chromium"
    try:
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    except:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# --- [UI] ---
st.set_page_config(page_title="URL Multi-Checker", layout="wide")
st.title("📌 통합 URL 상태 확인 (검색 기반 정밀 모드)")

selected_platforms = st.sidebar.multiselect("플랫폼 선택", ["pinterest.com", "trenbe.com", "mustit.co.kr", "11st.co.kr"], default=["trenbe.com"])
input_method = st.sidebar.radio("입력 방식", ["CSV 업로드", "구글 시트 URL"])

df = None
if input_method == "CSV 업로드":
    file = st.file_uploader("파일 선택", type=["csv"])
    if file: df = pd.read_csv(file, encoding='utf-8-sig')
else:
    gs_url = st.text_input("구글 시트 URL")
    if gs_url and "/d/" in gs_url:
        sid = gs_url.split("/d/")[1].split("/")[0]
        df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv")

if df is not None and selected_platforms:
    if st.button("분석 시작"):
        progress = st.progress(0)
        status_label = st.empty()
        
        needs_browser = any(p in selected_platforms for p in ["trenbe.com", "mustit.co.kr", "11st.co.kr"])
        driver = get_driver() if needs_browser else None
        
        for idx in range(len(df)):
            url = str(df.iloc[idx, 2])
            raw_p = str(df.iloc[idx, 13]).lower()
            result = "Skipped"

            try:
                if "pinterest.com" in selected_platforms and "pinterest" in raw_p:
                    result = check_pinterest_status(url)
                elif "trenbe.com" in selected_platforms and "trenbe" in raw_p:
                    result = check_trenbe_status(url, driver)
                elif "11st.co.kr" in selected_platforms and ("11st" in raw_p or "11번가" in raw_p):
                    result = check_11st_status(url, driver)
                elif "mustit.co.kr" in selected_platforms and "mustit" in raw_p:
                    result = check_mustit_status(url, driver)
            except: result = "Error"

            df.iloc[idx, 3] = result
            progress.progress((idx + 1) / len(df))
            status_label.text(f"[{idx+1}/{len(df)}] {raw_p} 분석 중... 결과: {result}")

        if driver: driver.quit()
        st.success("완료!")
        st.dataframe(df)
        st.download_button("결과 CSV 다운로드", df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "result.csv", "text/csv")
