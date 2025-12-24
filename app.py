# --- [Selenium 설정 강화] ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920x1080")
    
    # 봇 감지 방지를 위한 설정 추가
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
    
    # webdriver 속성 제거 (봇 탐지 우회)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

# --- [로직 2] 트렌비 검증 (상세페이지 직접 접속 최적화) ---
def check_trenbe_status(url, driver):
    try:
        driver.get(url)
        # 페이지 로딩을 위해 최소한의 시간 확보
        time.sleep(3) 
        
        # 1. '장바구니' 또는 '구매하기' 버튼 확인 (가장 확실한 Active 지표)
        # 텍스트가 포함된 버튼이나 span, div 등을 포괄적으로 찾습니다.
        active_selectors = [
            "//button[contains(., '장바구니')]",
            "//button[contains(., '바로구매')]",
            "//span[contains(., '장바구니')]",
            "//div[contains(text(), '장바구니')]"
        ]
        
        for selector in active_selectors:
            elements = driver.find_elements(By.XPATH, selector)
            if len(elements) > 0 and elements[0].is_displayed():
                return "Active"

        # 2. '판매 종료' 관련 키워드 확인 (Expired 지표)
        page_source = driver.page_source
        expired_keywords = ['판매가 종료된', '품절된 상품', '상품이 존재하지 않습니다', '정상적인 접근이 아닙니다', '결과가 없습니다']
        if any(kw in page_source for kw in expired_keywords):
            return "Expired"
        
        # 3. 만약 위에서 판단이 안 섰을 경우, 특정 구매 버튼 클래스 재확인 (트렌비 전용)
        if "btn_buy" in page_source or "btn_cart" in page_source:
            return "Active"

        return "Expired"
    except Exception as e:
        return f"Error"
