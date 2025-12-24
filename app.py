import streamlit as st
import pandas as pd
import requests
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- [로직 1] 핀터레스트 검증 (Requests 방식) ---
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

# --- [로직 2] 트렌비 검증 (상세 페이지 직접 접속 방식) ---
def check_trenbe_status(url, driver):
    try:
        driver.get(url)
        # 페이지 로딩 및 봇 감지 회피를 위한 대기
        time.sleep(4) 
        
        # 1. 구매 관련 버튼 확인 (Active 지표)
        # '구매', '장바구니'가 포함된 버튼 요소를 찾습니다.
        active_selectors = [
            "//button[contains(., '장바구니')]",
            "//button[contains(., '바로구매')]",
            "//span[contains(., '장바구니')]",
            "//div[contains(text(), '장바구니')]"
        ]
        
        for selector in active_selectors:
            elements = driver.find_elements(By.XPATH, selector)
            if len(elements) > 0:
                # 요소가 존재하고 화면에 보인다면 Active로 판정
                if any(el.is_displayed() for el in elements):
                    return "Active"

        # 2. 판매 종료/품절 텍스트 확인 (Expired 지표)
        page_source = driver.page_source
        expired_keywords = ['판매가 종료된', '품절된 상품', '상품이 존재하지 않습니다', '정상적인 접근이 아닙니다', '결과가 없습니다']
        if any(kw in page_source for kw in expired_keywords):
            return "Expired"
        
        # 3. 보조 확인: 버튼 클래스명 존재 여부
        if "btn_buy" in page_source or "btn_cart" in page_source:
            return "Active"

        return "Expired"
    except Exception as e:
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
        if "검색 결과가 없습니다" in page_source:
            return "Expired"
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
        is_exact_match = any(product_id in item.get_attribute('href') for item in items)
        return "Active" if is_exact_match else "Expired"
    except:
        return "Error"

# --- [로직 4] 머스트잇 검증 ---
def check_mustit_status(url, driver):
    try:
        driver.get(url)
        time.sleep(4)
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            alert.accept()
            if any(kw in alert_text for kw in ["관리자에 의해 삭제", "판매종료", "존재하지"]):
                return "Expired"
        except:
            pass
        if "redirector" in driver.current_url:
            return "Expired"
        if any(kw in driver.page_source for kw in ["판매종료된 상품", "존재하지 않는 상품"]):
            return "Expired"
        return "Active"
    except:
        return "Error"

# --- [Selenium 설정] 봇 탐지 우회 강화 ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920x1080")
    
    # 최신 User-Agent 및 자동화 감지 회피 설정
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    options.binary_location = "/usr/bin/chromium"
    
    try:
        driver = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    except:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # 브라우저 수준에서 webdriver 속성 숨기기
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

# --- [UI 및 실행부] ---
st.set_page_config(page_title="URL Multi-Checker", layout="wide")
st.title("📌 통합 URL 상태 확인 도구")

selected_platforms = st.sidebar.multiselect(
    "분석할 플랫폼을 선택하세요",
    ["pinterest.com", "trenbe.com", "mustit.co.kr", "11st.co.kr"],
    default=["pinterest.com", "trenbe.com"]
)

uploaded_file = st.file_uploader("분석할 CSV 파일을 업로드하세요", type=["csv"])

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
    except:
        df = pd.read_csv(uploaded_file, encoding='cp949')

    if st.button("분석 시작"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        needs_browser = any(p in selected_platforms for p in ["trenbe.com", "mustit.co.kr", "11st.co.kr"])
        driver = get_driver() if needs_browser else None
        
        total = len(df)
        for idx in range(total):
            url = str(df.iloc[idx, 2])          # C열
            platform = str(df.iloc[idx, 13]).lower() # N열
            
            result = "Skipped"
            
            if "pinterest.com" in selected_platforms and 'pinterest' in platform:
                result = check_pinterest_status(url)
            elif "trenbe.com" in selected_platforms and 'trenbe' in platform:
                result = check_trenbe_status(url, driver)
            elif "11st.co.kr" in selected_platforms and ('11st' in platform or '11번가' in platform):
                result = check_11st_status(url, driver)
            elif "mustit.co.kr" in selected_platforms and 'mustit' in platform:
                result = check_mustit_status(url, driver)
            
            df.iloc[idx, 3] = result # D열 기록
            
            progress = (idx + 1) / total
            progress_bar.progress(progress)
            status_text.text(f"진행 중: {idx+1}/{total} (플랫폼: {platform} | 결과: {result})")

        if driver: driver.quit()
        
        st.success("분석 완료!")
        st.dataframe(df.head(20))
        
        csv_data = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button(
            label="결과 파일(.csv) 다운로드",
            data=csv_data,
            file_name="url_check_result.csv",
            mime="text/csv"
        )
