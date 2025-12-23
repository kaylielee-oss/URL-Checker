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
        # 1. URL에서 상품 ID 추출
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        product_id = match.group()
        
        # 2. 검색 페이지 접속
        search_url = f"https://www.trenbe.com/search?keyword={product_id}"
        driver.get(search_url)
        time.sleep(4.5) 

        # 3. 검색 결과 내에서 실제 상품 링크 찾기
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        target_link = None
        for item in items:
            href = item.get_attribute('href') or ""
            # 정확히 해당 product_id를 포함하는 첫 번째 상품 링크를 확보
            if product_id in href:
                target_link = href
                break

        if not target_link:
            return "Expired" # 검색 결과에 아예 없음

        # 4. [핵심 추가] 상세 페이지로 직접 들어가서 최종 확인
        driver.get(target_link)
        time.sleep(3.5)
        
        final_page_source = driver.page_source
        
        # 판매 종료를 알리는 핵심 키워드들 (트렌비 상세페이지 기준)
        sold_out_keywords = [
            "판매가 종료되었습니다",
            "판매 종료",
            "품절된 상품입니다",
            "존재하지 않는 상품",
            "Sold Out"
        ]
        
        # 상세 페이지 주소 확인 (리다이렉트 여부)
        if "error" in driver.current_url.lower():
            return "Expired"

        # 문구 체크 및 구매 버튼 존재 여부 확인
        if any(kw in final_page_source for kw in sold_out_keywords):
            return "Expired"
        
        # 트렌비는 품절 시 보통 '구매하기' 버튼이 비활성화되거나 사라짐
        # (사이트 구조에 따라 추가 검증 가능)
        
        return "Active"

    except Exception as e:
        return "Error"

def check_11st_status(url, driver):
    try:
        # 1. 상세 페이지 직접 접속
        driver.get(url)
        time.sleep(4) # 팝업 및 안내 문구 로딩 대기
        
        # 2. 페이지 소스 획득
        page_source = driver.page_source
        
        # 3. 판매 종료를 알리는 핵심 키워드 (11번가 특화)
        # 11번가는 판매 종료 시 팝업이나 상단 바에 아래 문구들이 뜹니다.
        stop_keywords = [
            "판매가 종료되었습니다",
            "판매 종료",
            "판매중단",
            "판매 중단",
            "상품이 존재하지 않습니다",
            "해당 상품은 판매가 종료되었습니다",
            "페이지를 찾을 수 없습니다"
        ]
        
        # 4. 검증 로직
        # 문구 체크
        if any(kw in page_source for kw in stop_keywords):
            return "Expired"
            
        # 5. [추가 검증] 구매 버튼 상태 확인
        # 11번가는 품절/종료 시 구매 버튼 텍스트가 '판매종료'로 바뀌거나 버튼이 비활성화됩니다.
        try:
            # 장바구니나 구매하기 버튼 영역에서 종료 문구가 있는지 재확인
            buy_area = driver.find_element(By.CSS_SELECTOR, ".c_product_btn_box, .method").text
            if "판매종료" in buy_area or "판매중단" in buy_area:
                return "Expired"
        except:
            pass # 버튼 영역을 못 찾아도 문구 체크가 우선이므로 넘어감

        return "Active"
        
    except Exception as e:
        return "Error"

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
    options.add_argument("--headless")  # 서버에선 창이 뜨지 않아야 함
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Streamlit Cloud 환경에서 크롬 실행 파일 경로 지정
    options.binary_location = "/usr/bin/chromium"
    
    try:
        # 1. 시스템 설치된 드라이버 우선 시도 (Streamlit Cloud용)
        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=options)
    except:
        # 2. 로컬 테스트용 (내 컴퓨터 실행 시)
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
