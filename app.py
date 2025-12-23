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
        # 1. 상세 페이지 직접 접속 (검색 과정을 거치지 않고 바로 진입)
        driver.get(url)
        time.sleep(5)  # 트렌비는 보안 및 동적 로딩이 강하므로 충분히 대기
        
        current_url = driver.current_url
        page_source = driver.page_source

        # [검증 A] 에러 페이지로 리다이렉트 되었는지 확인
        if "error" in current_url.lower() or "404" in page_source:
            return "Expired"

        # [검증 B] 판매 종료를 알리는 결정적 문구들
        # 이 문구들이 '없어야' Active입니다.
        sold_out_indicators = [
            "판매가 종료되었습니다",
            "판매 종료",
            "존재하지 않는 상품",
            "품절된 상품입니다",
            "해당 상품은 판매가 종료"
        ]
        
        # 페이지 소스 내에 위 종료 문구가 하나라도 포함되어 있는지 확인
        if any(kw in page_source for kw in sold_out_indicators):
            return "Expired"

        # [검증 C] 구매 버튼 존재 여부 확인 (최종 확인)
        # 트렌비 상세페이지의 구매하기 버튼이나 장바구니 버튼의 텍스트/클래스를 확인합니다.
        try:
            # 트렌비 구매 버튼 영역 (클래스명은 사이트 업데이트에 따라 변할 수 있음)
            # 버튼 영역이 존재하고 그 안에 '판매 종료'라는 글자가 없다면 살아있는 것으로 간주
            buy_btn = driver.find_element(By.CSS_SELECTOR, "body").text
            if "구매하기" in buy_btn or "장바구니" in buy_btn:
                return "Active"
        except:
            pass

        # 위 문구들이 없고 페이지가 정상적이라면 Active로 판정
        return "Active"
        
    except Exception as e:
        return "Error"


        def check_11st_status(url, driver):
    try:
        # 1. 상세 페이지 접속
        driver.get(url)
        time.sleep(5)  # 팝업이 뜨는 시간을 충분히 기다림
        
        # 2. 강제 팝업 확인 (가장 확실한 방법)
        # 11번가 판매종료 안내창은 보통 특정 클래스나 ID를 가짐
        page_source = driver.page_source
        
        # 판매 종료를 나타내는 결정적 텍스트들
        expired_indicators = [
            "판매가 종료되었습니다",
            "판매종료",
            "판매중단",
            "상품이 존재하지 않습니다",
            "유효하지 않은 상품",
            "판매가 중단된 상품"
        ]
        
        # [방법 A] 페이지 전체 텍스트에서 검사
        if any(kw in page_source for kw in expired_indicators):
            return "Expired"
            
        # [방법 B] 구매/장바구니 버튼의 상태를 직접 확인 (버튼이 없거나 비활성화면 종료)
        try:
            # 11번가의 '구매하기' 혹은 '장바구니' 관련 버튼들을 찾음
            # 판매 종료 상품은 이 버튼들이 '판매종료' 텍스트로 바뀌거나 숨겨짐
            btn_text = driver.find_element(By.CSS_SELECTOR, "div.c_product_btn_box, div.method, a.btn_buy").text
            if "판매종료" in btn_text or "판매중단" in btn_text:
                return "Expired"
        except:
            # 버튼 영역 자체가 아예 안 보인다면 종료된 것으로 간주
            return "Expired"

        # [방법 C] 현재 URL 확인 (에러 페이지나 메인으로 튕겼는지)
        if "error" in driver.current_url or driver.current_url == "https://www.11st.co.kr/":
            return "Expired"

        return "Active"
        
    except Exception as e:
        return "Error"

def check_mustit_status(url, driver):
    try:
        # 1. 타임아웃 설정 및 페이지 접속
        driver.set_page_load_timeout(20) # 페이지 로딩이 너무 길어지면 에러 대신 다음으로 진행
        driver.get(url)
        time.sleep(5) # 팝업/알림창이 뜨는 시간을 충분히 확보
        
        # 2. 브라우저 알림창(Alert) 확인 로직 추가
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            # 알림창 문구 확인
            if any(kw in alert_text for kw in ["관리자에 의해 삭제", "판매종료", "존재하지 않는"]):
                alert.accept() # 알림창 닫기
                return "Expired"
            alert.accept()
        except:
            # 알림창이 없는 경우 통과
            pass

        # 3. URL 및 페이지 소스 확인
        current_url = driver.current_url
        page_source = driver.page_source
        
        # URL 리다이렉션 감지 (주소에 특정 키워드가 포함되면 만료)
        decoded_url = urllib.parse.unquote(current_url)
        if "redirector" in current_url or "판매종료" in decoded_url or "etc/error" in current_url:
            return "Expired"
            
        # 페이지 내 텍스트 확인 (요청하신 '관리자에 의해 삭제된 상품' 포함)
        expired_keywords = [
            "관리자에 의해 삭제된 상품",
            "판매종료된 상품",
            "존재하지 않는 상품",
            "판매가 종료된",
            "삭제된 상품"
        ]
        
        if any(kw in page_source for kw in expired_keywords):
            return "Expired"
            
        return "Active"
        
    except Exception as e:
        # 에러 발생 시 상세 이유를 로그로 남기되, 
        # 페이지 로드 실패 자체가 종료된 상품의 징후일 수 있으므로 다시 한번 체크 시도
        return "Error"

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
