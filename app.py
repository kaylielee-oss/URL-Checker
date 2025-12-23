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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- [드라이버 설정: 봇 감지 우회 및 최적화] ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920x1080")
    # 최신 User-Agent 사용
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # 이미지 로딩 차단 (속도 향상)
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except:
        options.binary_location = "/usr/bin/chromium"
        driver = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    return driver

# --- [플랫폼별 정밀 검증 로직] ---

def check_trenbe_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        p_id = match.group()
        
        driver.get(f"https://www.trenbe.com/search?keyword={p_id}")
        # 검색 결과가 그려질 때까지 최대 7초 대기
        time.sleep(4) 
        
        # 1. '결과 없음' 박스 확인
        no_result = driver.find_elements(By.CSS_SELECTOR, ".no-result-box, .search_no_result")
        if no_result and "결과가 없습니다" in driver.page_source:
            return "Expired"
            
        # 2. 결과 리스트 대조 (정확히 내 ID가 포함된 상품 카드가 있는지)
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        for item in items:
            if p_id in (item.get_attribute('href') or ""):
                return "Active"
        return "Expired"
    except: return "Error"

def check_11st_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        p_id = match.group()
        
        driver.get(f"https://search.11st.co.kr/Search.tmall?kwd={p_id}")
        time.sleep(3.5)
        
        if "검색 결과가 없습니다" in driver.page_source:
            return "Expired"
            
        # 실제 상품 리스트 영역에서 ID 대조
        product_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
        if any(p_id in (link.get_attribute('href') or "") for link in product_links):
            return "Active"
        return "Expired"
    except: return "Error"

def check_mustit_status(url, driver):
    try:
        driver.get(url)
        time.sleep(4)
        # 알림창 처리
        try:
            alert = driver.switch_to.alert
            txt = alert.text
            alert.accept()
            if any(k in txt for k in ["삭제", "종료", "존재하지"]): return "Expired"
        except: pass
        
        if "redirector" in driver.current_url or "etc/error" in driver.current_url: return "Expired"
        if any(k in driver.page_source for k in ["판매종료", "삭제된 상품", "존재하지 않는"]): return "Expired"
        return "Active"
    except: return "Error"

# --- [UI 및 데이터 처리 메인] ---

st.set_page_config(page_title="URL Checker Pro", layout="wide")
st.title("🎯 정밀 URL 상태 확인 도구")

uploaded_file = st.file_uploader("CSV 파일 업로드", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
    cols = df.columns.tolist()
    
    st.sidebar.header("열 매핑 설정")
    url_col = st.sidebar.selectbox("URL 열 (C열 등)", cols, index=min(2, len(cols)-1))
    plat_col = st.sidebar.selectbox("플랫폼 이름 열 (N열 등)", cols, index=min(13, len(cols)-1))
    res_col = st.sidebar.selectbox("결과 저장 열 (D열 등)", cols, index=min(3, len(cols)-1))

    if st.button("🚀 분석 시작"):
        driver = get_driver()
        progress_bar = st.progress(0)
        
        for idx in range(len(df)):
            url = str(df.at[idx, url_col])
            platform = str(df.at[idx, plat_col]).lower()
            
            result = "Skipped"
            if "trenbe" in platform: result = check_trenbe_status(url, driver)
            elif "11st" in platform or "11번가" in platform: result = check_11st_status(url, driver)
            elif "mustit" in platform: result = check_mustit_status(url, driver)
            elif "pinterest" in platform:
                # 핀터레스트는 Requests로 처리
                try:
                    res = requests.get(url, timeout=10)
                    result = "Active" if res.status_code == 200 else "Dead"
                except: result = "Error"

            # 데이터프레임에 정확하게 기록
            df.at[idx, res_col] = result
            
            # 진행 상태 업데이트
            progress_bar.progress((idx + 1) / len(df))
            st.write(f"[{idx+1}/{len(df)}] {url} -> {result}")

        driver.quit()
        st.success("완료!")
        st.dataframe(df)
        
        csv_out = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button("📥 결과 CSV 다운로드", csv_out, "checked_result.csv", "text/csv")
