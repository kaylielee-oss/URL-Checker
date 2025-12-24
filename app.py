import streamlit as st
import pandas as pd
import requests
import time
import re
import json
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# 1. 페이지 설정
st.set_page_config(page_title="통합 URL 상태 확인 도구", layout="wide")

# --- [로직 1] 트렌비 고정밀 검증 (검색+상세페이지 교차 검증) ---
def check_trenbe_status(url, driver):
    try:
        # URL에서 상품 번호(ID) 추출
        match = re.search(r'(\d+)', str(url))
        if not match: return "Invalid URL"
        product_id = match.group(1)

        # [단계 1] 검색 결과 페이지 검증 (1차 필터링)
        search_url = f"https://www.trenbe.com/search?keyword={product_id}"
        driver.get(search_url)
        time.sleep(random.uniform(4.0, 5.5)) 

        search_source = driver.page_source
        # '결과가 없습니다' 문구 확인
        no_result = any(kw in search_source for kw in ['검색 결과가 없습니다', '결과가 없습니다'])
        
        # 실제 상품 리스트 내에 해당 ID가 있는지 대조 (추천 상품 배제)
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        is_in_search = any(product_id in (item.get_attribute('href') or "") for item in items)

        if no_result or not is_in_search:
            return "Expired"

        # [단계 2] 상세 페이지 버튼 가시성 검증 (2차 확정)
        driver.get(url)
        time.sleep(random.uniform(5.0, 6.5))
        
        detail_source = driver.page_source
        # 상세 페이지 특유의 종료 안내 레이어 확인
        if any(kw in detail_source for kw in ['판매가 종료된 상품입니다', '품절된 상품입니다']):
            return "Expired"

        try:
            # 메인 구매 버튼 영역 텍스트 분석
            cta_area = driver.find_element(By.CSS_SELECTOR, "div[class*='ProductDetail_button_group'], div[class*='cta_area']")
            cta_text = cta_area.text
            if any(kw in cta_text for kw in ['장바구니', '바로구매', 'BUY NOW']):
                if not any(kw in cta_text for kw in ['종료', '품절']):
                    return "Active"
        except:
            pass

        return "Expired"
    except:
        return "Error"

# --- [로직 2] 머스트잇 정밀 검증 ---
def check_mustit_status(url, driver):
    try:
        driver.get(url)
        time.sleep(random.uniform(4.0, 6.0))
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            alert.accept()
            if any(kw in alert_text for kw in ["관리자에 의해 삭제", "판매종료", "존재하지"]):
                return "Expired"
        except: pass

        if "redirector" in driver.current_url or "mustit.co.kr/main" in driver.current_url:
            return "Expired"

        page_source = driver.page_source
        if any(kw in page_source for kw in ["장바구니", "구매하기", "BUY NOW"]):
            return "Active"
        return "Expired"
    except: return "Error"

# --- [로직 3] 핀터레스트/11번가 ---
def check_pinterest_status(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        pin_id = url.strip('/').split('/')[-1]
        if response.status_code == 200 and pin_id in response.url:
            if 'pinterestapp:pin' in response.text or 'og:title' in response.text:
                return "Active"
        return "Dead"
    except: return "Error"

def check_11st_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        product_id = match.group() if match else ""
        driver.get(f"https://search.11st.co.kr/Search.tmall?kwd={product_id}")
        time.sleep(5)
        if "검색 결과가 없습니다" in driver.page_source: return "Expired"
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
        return "Active" if any(product_id in item.get_attribute('href') for item in items) else "Expired"
    except: return "Error"

# --- [Selenium] 우회 설정 및 드라이버 생성 ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled") 
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.binary_location = "/usr/bin/chromium"
    try:
        driver = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    except:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    }) 
    return driver

# --- [UI 실행부] ---
st.title("📌 통합 URL 고정밀 확인 도구")

selected_platforms = st.sidebar.multiselect(
    "분석할 플랫폼을 선택하세요",
    ["pinterest.com", "trenbe.com", "mustit.co.kr", "11st.co.kr"],
    default=["trenbe.com", "mustit.co.kr"]
)

uploaded_file = st.file_uploader("분석할 CSV 파일을 업로드하세요", type=["csv"])

if uploaded_file is not None:
    try: df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
    except: df = pd.read_csv(uploaded_file, encoding='cp949')

    if st.button("분석 시작"):
        df.iloc[:, 3] = "" 
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        needs_browser = any(p in selected_platforms for p in ["trenbe.com", "mustit.co.kr", "11st.co.kr"])
        driver = get_driver() if needs_browser else None
        
        for idx in range(len(df)):
            url = str(df.iloc[idx, 2])          
            platform_info = str(df.iloc[idx, 13]).lower()
            result = "Skipped"
            
            if "trenbe.com" in selected_platforms and 'trenbe' in platform_info:
                result = check_trenbe_status(url, driver)
            elif "mustit.co.kr" in selected_platforms and 'mustit' in platform_info:
                result = check_mustit_status(url, driver)
            elif "pinterest.com" in selected_platforms and 'pinterest' in platform_info:
                result = check_pinterest_status(url)
            elif "11st.co.kr" in selected_platforms and '11st' in platform_info:
                result = check_11st_status(url, driver)
            
            df.iloc[idx, 3] = result 
            progress_bar.progress((idx + 1) / len(df))
            status_text.text(f"진행 중: {idx+1}/{len(df)} | 플랫폼: {platform_info} | 결과: {result}")
            time.sleep(random.uniform(1.0, 2.0)) 

        if driver: driver.quit()
        st.success("분석이 완료되었습니다!")
        st.dataframe(df.head(20))
        st.download_button("결과 다운로드", df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "result.csv", "text/csv")
