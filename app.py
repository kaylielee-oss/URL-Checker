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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 1. 페이지 설정
st.set_page_config(page_title="통합 URL 상태 확인 도구", layout="wide")

# --- [로직 1] 트렌비 정밀 검증 (교차 검증 및 명시적 대기) ---
def check_trenbe_status(url, driver):
    try:
        # [준비] 상품 번호 추출
        match = re.search(r'(\d+)', str(url))
        product_id = match.group(1) if match else ""

        # --- [단계 1] 검색 페이지 확인 (보조 지표) ---
        search_url = f"https://www.trenbe.com/search?keyword={product_id}"
        driver.get(search_url)
        time.sleep(random.uniform(3.0, 4.0)) 
        
        search_source = driver.page_source
        # 검색 결과에 내 상품 ID가 포함된 카드가 하나라도 있는지 확인
        is_found_in_search = product_id in search_source and "결과가 없습니다" not in search_source

        # --- [단계 2] 상세 페이지 접속 및 정밀 판별 ---
        driver.get(url)
        # 명시적 대기: 주요 버튼 영역이 나타날 때까지 최대 10초 대기
        wait = WebDriverWait(driver, 10)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='button_group'], div[class*='cta_area'], button")))
        except:
            pass
            
        time.sleep(2) # 동적 텍스트 렌더링 완료를 위한 추가 대기
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        page_source = driver.page_source

        # [판별 1] 명확한 종료 문구가 본문에 보이면 즉시 Expired
        expired_keywords = ['판매가 종료된 상품입니다', '품절된 상품입니다', '존재하지 않는 상품', '정상적인 접근이 아닙니다']
        if any(kw in page_text for kw in expired_keywords):
            return "Expired"

        # [판별 2] 메인 구매 버튼 영역 분석
        active_keywords = ['장바구니', '바로구매', 'BUY NOW', '구매하기', '쇼핑백']
        try:
            # 추천 상품 영역을 제외한 실제 구매 섹션 타겟팅
            cta_area = driver.find_element(By.CSS_SELECTOR, "div[class*='button_group'], div[class*='cta_area'], div[class*='bottom_tab']")
            cta_text = cta_area.text
            if any(kw in cta_text for kw in active_keywords):
                # 버튼 영역에 '품절'이나 '종료'가 같이 적혀있는지 재확인
                if not any(kw in cta_text for kw in ['종료', '품절']):
                    return "Active"
        except:
            pass

        # [판별 3] 검색 결과가 있었고, 본문에 구매 키워드가 살아있다면 Active
        if is_found_in_search and any(kw in page_text for kw in active_keywords):
            if "판매가 종료" not in page_text:
                return "Active"

        return "Expired"
    except Exception as e:
        return "Error"

# --- [로직 2] 머스트잇 / [로직 3] 기타 플랫폼 (기존 완성본 유지) ---
def check_mustit_status(url, driver):
    try:
        driver.get(url)
        time.sleep(random.uniform(4.0, 6.0))
        try:
            alert = driver.switch_to.alert
            alert.accept()
            return "Expired"
        except: pass
        if "redirector" in driver.current_url or "mustit.co.kr/main" in driver.current_url:
            return "Expired"
        if any(kw in driver.page_source for kw in ["장바구니", "구매하기", "BUY NOW"]):
            return "Active"
        return "Expired"
    except: return "Error"

def check_pinterest_status(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        pin_id = url.strip('/').split('/')[-1]
        if response.status_code == 200 and pin_id in response.url:
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
        return "Active"
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
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
    except:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    }) 
    return driver

# --- [UI 메인 실행부] ---
st.title("📌 통합 URL 고정밀 확인 도구 (최종 보정판)")

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
            status_text.text(f"진행 중: {idx+1}/{len(df)} | 결과: {result}")
            time.sleep(random.uniform(1.0, 2.0)) 

        if driver: driver.quit()
        st.success("모든 분석이 완료되었습니다!")
        st.dataframe(df.head(20))
        st.download_button("결과 파일 다운로드", df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "checked_result.csv", "text/csv")
