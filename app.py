import streamlit as st
import pandas as pd
import requests
import time
import re
import io
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- [로직 1] 핀터레스트 검증 ---
def check_pinterest_status(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        if response.status_code == 200 and ('pinterestapp:pin' in response.text or 'og:title' in response.text):
            return "Active"
        return "Dead"
    except:
        return "Error"

# --- [로직 2] 통합 커머스 검증 (트렌비, 머스트잇, 11번가) ---
def check_commerce_status(url, platform, driver):
    try:
        # 1. URL에서 상품ID(숫자) 추출
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        product_id = match.group()

        # 2. 플랫폼별 검증 로직
        if 'mustit' in platform:
            # 머스트잇은 상세 페이지로 접속하여 리다이렉션 여부 확인
            driver.get(url) 
            time.sleep(3) # 리다이렉트 대기
            current_url = driver.current_url
            
            # URL에 redirector가 포함되어 있거나 판매종료 메시지가 인코딩되어 포함된 경우
            if "redirector" in current_url or "판매종료" in urllib.parse.unquote(current_url):
                return "Expired"
            
            # 페이지 소스 내에 종료 문구 재확인
            if "판매종료된 상품" in driver.page_source:
                return "Expired"
            return "Active"

        elif '11st' in platform or '11번가' in platform:
            # 11번가는 상품번호 검색 결과로 확인
            search_url = f"https://search.11st.co.kr/Search.tmall?kwd={product_id}"
            driver.get(search_url)
            time.sleep(3.5)
            
            if f"{product_id}의 검색 결과가 없습니다" in driver.page_source or "검색 결과가 없습니다" in driver.page_source:
                return "Expired"
            return "Active"

        elif 'trenbe' in platform:
            search_url = f"https://www.trenbe.com/search?keyword={product_id}"
            driver.get(search_url)
            time.sleep(4)
            if any(kw in driver.page_source for kw in ['검색 결과가 없습니다', '결과가 없습니다']):
                return "Expired"
            return "Active"

        return "Unsupported Platform"
    except Exception as e:
        return f"Error: {str(e)}"

# --- [Selenium 설정] ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except:
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
    return driver

# --- [UI 구성] ---
st.set_page_config(page_title="URL Checker Pro", layout="wide")
st.title("📌 통합 URL 상태 확인 (Pinterest, Trenbe, MustIt, 11st)")

input_method = st.radio("데이터 입력 방식", ["CSV 파일 업로드", "구글 스프레드시트 URL 입력"])
df = None

if input_method == "CSV 파일 업로드":
    uploaded_file = st.file_uploader("CSV 파일 선택", type=["csv"])
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
        except:
            df = pd.read_csv(uploaded_file, encoding='cp949')

elif input_method == "구글 스프레드시트 URL 입력":
    sheet_url = st.text_input("스프레드시트 주소 (공유 설정 확인 요망)")
    if sheet_url and "/d/" in sheet_url:
        sheet_id = sheet_url.split("/d/")[1].split("/")[0]
        df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv")

if df is not None:
    st.write(f"데이터 로드 완료: {len(df)}행")
    if st.button("분석 시작"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        driver = get_driver()
        total = len(df)
        
        for idx in range(total):
            url = df.iloc[idx, 2]         # C열
            platform = str(df.iloc[idx, 13]).lower() # N열
            
            if 'pinterest' in platform:
                result = check_pinterest_status(url)
            else:
                result = check_commerce_status(url, platform, driver)
            
            df.iloc[idx, 3] = result      # D열 저장
            
            progress_bar.progress((idx + 1) / total)
            status_text.text(f"[{idx+1}/{total}] {platform} 검사 중... 결과: {result}")

        driver.quit()
        st.success("분석이 완료되었습니다!")
        st.dataframe(df)

        # 엑셀 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("결과 엑셀(.xlsx) 다운로드", output.getvalue(), "final_result.xlsx")
