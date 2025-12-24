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

# --- [로직 2] 트렌비 검증 (구조화 데이터 분석 방식) ---
def check_trenbe_status(url, driver):
    try:
        driver.get(url)
        time.sleep(4) # 충분한 데이터 로드 대기
        
        page_source = driver.page_source
        
        # [단계 1] JSON-LD 메타데이터에서 상태 추출 (가장 정확)
        scripts = driver.find_elements(By.XPATH, "//script[@type='application/ld+json']")
        for script in scripts:
            try:
                data = json.loads(script.get_attribute('innerHTML'))
                # 단일 객체 혹은 리스트 형태 대응
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get('@type') == 'Product' or 'offers' in item:
                        availability = item.get('offers', {}).get('availability', '')
                        if 'InStock' in availability:
                            return "Active"
                        elif 'OutOfStock' in availability:
                            return "Expired"
            except:
                continue

        # [단계 2] 텍스트 기반 2차 검증 (추천 상품 제외를 위해 본문 텍스트 분석)
        # 트렌비는 품절 시 '판매가 종료된 상품입니다' 혹은 '재입고 알림' 버튼이 나타남
        body_text = driver.find_element(By.TAG_NAME, "body").text
        
        expired_keywords = ['판매가 종료된', '품절된 상품', '상품이 존재하지 않습니다', '정상적인 접근이 아닙니다']
        if any(kw in body_text for kw in expired_keywords):
            return "Expired"
        
        active_keywords = ['장바구니', '바로구매', 'BUY NOW']
        if any(kw in body_text for kw in active_keywords):
            return "Active"

        return "Expired"
    except:
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
            alert.accept()
        except:
            pass
        if "redirector" in driver.current_url or any(kw in driver.page_source for kw in ["판매종료", "존재하지"]):
            return "Expired"
        return "Active"
    except:
        return "Error"

# --- [Selenium 설정] 봇 차단 우회 ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add
