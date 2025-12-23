import streamlit as st
import pandas as pd  # import pd as pd 대신 이렇게 수정해야 합니다.
import time
import re
import io
import urllib.parse
import requests
from selenium import webdriver
# ... 나머지 import 문 동일
# --- [1. 플랫폼별 정밀 로직 함수] ---

def check_pinterest_status(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        # 핀터레스트는 브라우저 없이 빠르게 확인
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        pin_id = url.strip('/').split('/')[-1].split('?')[0]
        if response.status_code == 200 and pin_id in response.url:
            if 'pinterestapp:pin' in response.text or 'og:title' in response.text:
                return "Active"
        return "Dead"
    except: return "Error"

def check_trenbe_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        p_id = match.group()
        driver.get(f"https://www.trenbe.com/search?keyword={p_id}")
        # WebDriverWait으로 로딩 최적화
        try:
            WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/product/'], .no-result-box")))
        except: pass
        
        page_source = driver.page_source
        if any(kw in page_source for kw in ["검색 결과가 없습니다", "결과가 없습니다"]):
            return "Expired"
        items = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        if any(p_id in (item.get_attribute('href') or "") for item in items):
            return "Active"
        return "Expired"
    except: return "Error"

def check_11st_status(url, driver):
    try:
        match = re.search(r'\d+', str(url))
        if not match: return "Invalid URL"
        p_id = match.group()
        driver.get(f"https://search.11st.co.kr/Search.tmall?kwd={p_id}")
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".l_search_content, .no_result")))
        except: pass
        
        if "검색 결과가 없습니다" in driver.page_source:
            return "Expired"
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
        if any(p_id in (link.get_attribute('href') or "") for link in links):
            return "Active"
        return "Expired"
    except: return "Error"

def check_mustit_status(url, driver):
    try:
        driver.get(url)
        time.sleep(4)
        try:
            alert = driver.switch_to.alert
            txt = alert.text
            alert.accept()
            if any(k in txt for k in ["삭제", "종료", "존재하지"]): return "Expired"
        except: pass
        
        if "redirector" in driver.current_url or "etc/error" in driver.current_url: return "Expired"
        if any(k in driver.page_source for k in ["관리자에 의해 삭제", "판매종료된 상품"]): return "Expired"
        return "Active"
    except: return "Error"

# --- [2. 드라이버 설정] ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    options.binary_location = "/usr/bin/chromium"
    try:
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    except:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# --- [3. 메인 UI 및 실행 로직] ---
st.set_page_config(page_title="URL Checker All-in-One", layout="wide")
st.title("🚀 통합 URL 상태 확인 도구 (최종 정밀 버전)")

# 사이드바 설정
st.sidebar.header("⚙️ 설정")
selected_platforms = st.sidebar.multiselect(
    "1. 분석할 플랫폼 선택",
    ["pinterest.com", "trenbe.com", "mustit.co.kr", "11st.co.kr"],
    default=["pinterest.com", "trenbe.com"]
)

input_method = st.sidebar.radio("2. 입력 방식 선택", ["CSV 업로드", "구글 시트 URL"])

df = None
if input_method == "CSV 업로드":
    file = st.file_uploader("CSV 파일 업로드", type=["csv"])
    if file:
        try: df = pd.read_csv(file, encoding='utf-8-sig')
        except: df = pd.read_csv(file, encoding='cp949')
else:
    gs_url = st.text_input("구글 시트 URL 입력")
    if gs_url and "/d/" in gs_url:
        sid = gs_url.split("/d/")[1].split("/")[0]
        df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv")

if df is not None:
    cols = df.columns.tolist()
    st.sidebar.divider()
    st.sidebar.subheader("📍 열 이름 매핑")
    url_col = st.sidebar.selectbox("URL 열 선택", cols, index=min(2, len(cols)-1))
    plat_col = st.sidebar.selectbox("플랫폼 이름 열(N열)", cols, index=min(13, len(cols)-1))
    res_col = st.sidebar.selectbox("결과 저장 열(D열)", cols, index=min(3, len(cols)-1))

    if st.button("🔍 분석 시작"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 브라우저 필요 여부 체크
        needs_browser = any(p in selected_platforms for p in ["trenbe.com", "mustit.co.kr", "11st.co.kr"])
        driver = get_driver() if needs_browser else None
        
        for idx in range(len(df)):
            row_url = str(df.at[idx, url_col])
            row_platform = str(df.at[idx, plat_col]).lower()
            result = "Skipped"

            try:
                # 선택된 플랫폼이면서 데이터의 플랫폼 정보와 일치할 때만 실행
                if "pinterest.com" in selected_platforms and "pinterest" in row_platform:
                    result = check_pinterest_status(row_url)
                elif "trenbe.com" in selected_platforms and "trenbe" in row_platform:
                    result = check_trenbe_status(row_url, driver)
                elif "11st.co.kr" in selected_platforms and ("11st" in row_platform or "11번가" in row_platform):
                    result = check_11st_status(row_url, driver)
                elif "mustit.co.kr" in selected_platforms and "mustit" in row_platform:
                    result = check_mustit_status(row_url, driver)
            except:
                result = "Error"

            # 데이터프레임의 정확한 위치에 기록
            df.at[idx, res_col] = result
            progress_bar.progress((idx + 1) / len(df))
            status_text.text(f"[{idx+1}/{len(df)}] 처리 중: {row_platform} | 결과: {result}")

        if driver: driver.quit()
        st.success("🎉 분석 완료!")
        st.dataframe(df)
        st.download_button("📥 결과 다운로드", df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "final_results.csv", "text/csv")
