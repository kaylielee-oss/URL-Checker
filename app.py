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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 1. 페이지 설정
st.set_page_config(page_title="URL Multi-Checker", layout="wide")

# --- [로직] 트렌비 정밀 검증 함수 ---
def check_trenbe_status(url, driver):
    try:
        driver.get(url)
        # 트렌비의 동적 텍스트 및 버튼 렌더링을 위해 충분히 대기
        time.sleep(6) 
        
        # [단계 1] 페이지 전체 소스에서 '확실한 종료 문구' 체크
        page_source = driver.page_source
        expired_keywords = [
            '판매가 종료된 상품입니다', 
            '품절된 상품입니다', 
            '정상적인 접근이 아닙니다',
            '상품이 존재하지 않습니다'
        ]
        if any(kw in page_source for kw in expired_keywords):
            return "Expired"

        # [단계 2] 메인 구매 영역(CTA) 집중 분석
        # 하단 추천 상품 영역과 섞이지 않도록 구매 버튼이 위치한 상단 영역만 타겟팅합니다.
        try:
            # 트렌비 구매 섹션의 주요 선택자들
            cta_selectors = [
                "div[class*='ProductDetail_button_group']",
                "div[class*='ProductDetail_bottom_tab']",
                "div[class*='cta_area']"
            ]
            
            cta_text = ""
            for selector in cta_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    if el.is_displayed(): # 실제로 화면에 보이는 영역의 텍스트만 수집
                        cta_text += el.text + " "
            
            # 수집된 메인 영역 텍스트로 판별
            if any(kw in cta_text for kw in ['판매 종료', '품절', '판매가 종료']):
                return "Expired"
            
            if any(kw in cta_text for kw in ['장바구니', '바로구매', 'BUY NOW', '구매하기']):
                return "Active"
        except:
            pass

        # [단계 3] 최후의 수단: 버튼 클래스 존재 여부 확인
        # 버튼 텍스트가 안 읽히더라도 클래스명에 'buy'나 'cart'가 살아있는지 확인합니다.
        if "btn_buy" in page_source or "btn_cart" in page_source:
            return "Active"
            
        return "Expired" # 모든 조건에 해당하지 않으면 보수적으로 Expired 처리
    except:
        return "Error"

# --- [기타 플랫폼 함수] ---
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

# --- [Selenium 설정] Streamlit Cloud 최적화 ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    # 자동화 감지 우회 설정
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    options.binary_location = "/usr/bin/chromium"
    try:
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
    except:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # 브라우저에서 webdriver 속성 제거
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

# --- [UI 메인] ---
st.title("📌 통합 URL 상태 확인 도구 (최종 보완판)")

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
        # 결과 기록을 위한 D열 초기화
        df.iloc[:, 3] = "" 
        
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
            
            df.iloc[idx, 3] = result 
            progress_bar.progress((idx + 1) / len(df))
            status_text.text(f"진행 중: {idx+1}/{len(df)} | 결과: {result}")

        if driver: driver.quit()
        st.success("분석이 완료되었습니다!")
        st.dataframe(df.head(20))
        st.download_button("결과 다운로드", df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "result.csv", "text/csv")
