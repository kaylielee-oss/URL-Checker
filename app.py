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

# --- [로직 1: pinterest.com 전용] ---
def check_pinterest_status(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        if response.status_code == 200 and ('pinterestapp:pin' in response.text or 'og:title' in response.text):
            return "Active"
        return "Dead"
    except:
        return "Error"

# --- [드라이버 설정] ---
def get_driver(selected_modes):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # 트렌비가 포함되어 있으면 창 크기와 에이전트 강화
    if "trenbe.com" in selected_modes:
        options.add_argument("window-size=1920x1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    else:
        options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    
    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except:
        options.binary_location = "/usr/bin/chromium"
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)

# --- [UI 구성] ---
st.set_page_config(page_title="URL Checker Pro (Multi)", layout="wide")
st.title("🔍 통합 상품 상태 확인 도구 (다중 선택 모드)")

# 1. 사이드바 다중 선택 메뉴
selected_modes = st.sidebar.multiselect(
    "1. 분석할 플랫폼을 선택하세요 (다중 선택 가능)",
    ["pinterest.com", "trenbe.com", "mustit.co.kr", "11st.co.kr"],
    default=["pinterest.com"]
)

input_method = st.sidebar.radio("2. 입력 방식 선택", ["CSV 업로드", "구글 시트 URL"])

df = None

# 데이터 로드
if input_method == "CSV 업로드":
    file = st.file_uploader("CSV 파일 선택", type=["csv"])
    if file:
        try: df = pd.read_csv(file, encoding='utf-8-sig')
        except: df = pd.read_csv(file, encoding='cp949')
else:
    url = st.text_input("구글 시트 URL")
    if url and "/d/" in url:
        try:
            sid = url.split("/d/")[1].split("/")[0]
            df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv")
        except: st.error("시트를 불러올 수 없습니다.")

# 분석 시작
if df is not None and len(selected_modes) > 0:
    st.write(f"📊 로드된 데이터: {len(df)}행 | 선택된 모드: {', '.join(selected_modes)}")
    
    if st.button("🚀 선택한 플랫폼 분석 시작"):
        progress = st.progress(0)
        status_label = st.empty()
        
        # 브라우저가 필요한 플랫폼이 포함되어 있는지 확인
        needs_browser = any(m in selected_modes for m in ["trenbe.com", "mustit.co.kr", "11st.co.kr"])
        driver = get_driver(selected_modes) if needs_browser else None
        
        total_rows = len(df)
        for idx in range(total_rows):
            target_url = str(df.iloc[idx, 2]) # C열
            data_platform = str(df.iloc[idx, 13]).lower() # N열
            result = "Skipped"

            try:
                # 1. Pinterest (선택 시에만)
                if "pinterest.com" in selected_modes and 'pinterest' in data_platform:
                    result = check_pinterest_status(target_url)
                
                # 2. Trenbe
                elif "trenbe.com" in selected_modes and 'trenbe' in data_platform:
                    match = re.search(r'\d+', target_url)
                    if match:
                        p_id = match.group()
                        driver.get(f"https://www.trenbe.com/search?keyword={p_id}")
                        time.sleep(4.5)
                        if any(kw in driver.page_source for kw in ['검색 결과가 없습니다', '결과가 없습니다']):
                            result = "Expired"
                        else: result = "Active"

                # 3. Mustit
                elif "mustit.co.kr" in selected_modes and 'mustit' in data_platform:
                    driver.get(target_url)
                    time.sleep(3.5)
                    curr = driver.current_url
                    if "redirector" in curr or "판매종료" in urllib.parse.unquote(curr):
                        result = "Expired"
                    elif "판매종료된 상품" in driver.page_source:
                        result = "Expired"
                    else: result = "Active"

                # 4. 11st
                elif "11st.co.kr" in selected_modes and ('11st' in data_platform or '11번가' in data_platform):
                    match = re.search(r'\d+', target_url)
                    if match:
                        p_id = match.group()
                        driver.get(f"https://search.11st.co.kr/Search.tmall?kwd={p_id}")
                        time.sleep(3.5)
                        if "검색 결과가 없습니다" in driver.page_source:
                            result = "Expired"
                        else: result = "Active"

            except: result = "Error"

            # 결과 업데이트
            if result != "Skipped":
                df.iloc[idx, 3] = result
            
            progress.progress((idx + 1) / total_rows)
            status_label.text(f"[{idx+1}/{total_rows}] 진행 중... (현재 행 플랫폼: {data_platform} -> 결과: {result})")

        if driver: driver.quit()
        st.success("🎉 선택한 모든 플랫폼의 분석이 완료되었습니다!")
        st.dataframe(df)

        # 결과 다운로드
        csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button("📥 결과 CSV 다운로드", csv, "multi_check_result.csv", "text/csv")
else:
    if len(selected_modes) == 0:
        st.warning("⚠️ 왼쪽 사이드바에서 분석할 플랫폼을 최소 하나 이상 선택해 주세요.")
