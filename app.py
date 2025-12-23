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

# --- [로직 2: trenbe.com (상세 페이지 정밀 검증)] ---
def check_trenbe_status(url, driver):
    try:
        driver.get(url)
        time.sleep(5)
        page_source = driver.page_source
        if any(kw in page_source for kw in ["판매가 종료되었습니다", "판매 종료", "품절된 상품입니다", "Sold Out"]):
            return "Expired"
        # 구매 버튼 텍스트 확인으로 2차 검증
        if "구매하기" in driver.find_element(By.TAG_NAME, "body").text:
            return "Active"
        return "Expired"
    except:
        return "Error"

# --- [로직 3: 11st.co.kr (구매 버튼 & 팝업 검증)] ---
def check_11st_status(url, driver):
    try:
        driver.get(url)
        time.sleep(5)
        page_source = driver.page_source
        stop_keywords = ["판매가 종료되었습니다", "판매 종료", "판매중단", "상품이 존재하지 않습니다"]
        if any(kw in page_source for kw in stop_keywords):
            return "Expired"
        try:
            btn_text = driver.find_element(By.CSS_SELECTOR, "div.c_product_btn_box, div.method, a.btn_buy").text
            if "판매종료" in btn_text or "판매중단" in btn_text:
                return "Expired"
        except:
            pass
        return "Active"
    except:
        return "Error"

# --- [로직 4: mustit.co.kr (알림창 & 삭제 문구 검증)] ---
def check_mustit_status(url, driver):
    try:
        driver.set_page_load_timeout(20)
        driver.get(url)
        time.sleep(5)
        # 알림창(Alert) 확인
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            if any(kw in alert_text for kw in ["관리자에 의해 삭제", "판매종료", "존재하지 않는"]):
                alert.accept()
                return "Expired"
            alert.accept()
        except:
            pass
        
        curr = driver.current_url
        page_source = driver.page_source
        if "redirector" in curr or "판매종료" in urllib.parse.unquote(curr) or "etc/error" in curr:
            return "Expired"
        if any(kw in page_source for kw in ["관리자에 의해 삭제된 상품", "판매종료된 상품", "삭제된 상품"]):
            return "Expired"
        return "Active"
    except:
        return "Error"

# --- [드라이버 설정] ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Streamlit Cloud 환경 대응
    options.binary_location = "/usr/bin/chromium"
    try:
        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=options)
    except:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

# --- [UI 및 실행 루프] ---
st.set_page_config(page_title="URL Multi-Checker Pro", layout="wide")
st.title("🔍 통합 상품 상태 확인 도구 (정밀 버전)")

selected_platforms = st.sidebar.multiselect(
    "1. 분석할 플랫폼 선택",
    ["pinterest.com", "trenbe.com", "mustit.co.kr", "11st.co.kr"],
    default=["pinterest.com"]
)
input_method = st.sidebar.radio("2. 입력 방식 선택", ["CSV 업로드", "구글 시트 URL"])

df = None
if input_method == "CSV 업로드":
    file = st.file_uploader("CSV 파일 선택", type=["csv"])
    if file:
        try:
            df = pd.read_csv(file, encoding='utf-8-sig')
        except:
            df = pd.read_csv(file, encoding='cp949')
else:
    gs_url = st.text_input("구글 시트 URL")
    if gs_url and "/d/" in gs_url:
        sid = gs_url.split("/d/")[1].split("/")[0]
        df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv")

if df is not None and selected_platforms:
    if st.button("🚀 분석 시작"):
        progress = st.progress(0)
        status_label = st.empty()
        
        needs_browser = any(p in selected_platforms for p in ["trenbe.com", "mustit.co.kr", "11st.co.kr"])
        driver = get_driver() if needs_browser else None
        
        total = len(df)
        for idx in range(total):
            url = str(df.iloc[idx, 2])
            raw_platform = str(df.iloc[idx, 13]).lower()
            result = "Skipped"

            try:
                if "pinterest.com" in selected_platforms and "pinterest" in raw_platform:
                    result = check_pinterest_status(url)
                elif "trenbe.com" in selected_platforms and "trenbe" in raw_platform:
                    result = check_trenbe_status(url, driver)
                elif "11st.co.kr" in selected_platforms and ("11st" in raw_platform or "11번가" in raw_platform):
                    result = check_11st_status(url, driver)
                elif "mustit.co.kr" in selected_platforms and "mustit" in raw_platform:
                    result = check_mustit_status(url, driver)
            except:
                result = "Error"

            df.iloc[idx, 3] = result
            progress.progress((idx + 1) / total)
            status_label.text(f"[{idx+1}/{total}] {raw_platform} 확인 중... 결과: {result}")

        if driver: driver.quit()
        st.success("🎉 분석 완료!")
        st.dataframe(df)
        csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button("📥 결과 CSV 다운로드", csv, "final_result.csv", "text/csv")
