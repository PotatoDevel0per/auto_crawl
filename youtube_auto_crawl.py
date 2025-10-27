import time
from datetime import datetime
import re
from typing import List, Dict, Optional, Tuple

import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def infinite_scroll(driver, scroll_count):
    """
    지정된 횟수만큼 페이지를 아래로 스크롤하여 동적 콘텐츠를 로드합니다.

    :param driver: Selenium WebDriver 인스턴스
    :param scroll_count: 스크롤할 횟수
    """
    print(f"{scroll_count}회 스크롤을 시작합니다.")
    for i in range(scroll_count):
        # 현재 문서의 높이를 가져와서 해당 높이만큼 스크롤
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
        # 새 콘텐츠가 로드될 시간을 줍니다.
        time.sleep(2)
        print(f"{i + 1}회 스크롤 완료.")


def smart_scroll_until_no_new(driver, item_selector: str, max_scrolls: int = 30, pause: float = 1.5):
    """
    스크롤을 반복하여 새로운 아이템이 더 이상 로드되지 않을 때까지 시도합니다.

    :param driver: Selenium WebDriver 인스턴스
    :param item_selector: 수집 대상 요소의 CSS 선택자 (예: 'ytd-rich-grid-media')
    :param max_scrolls: 최대 스크롤 횟수
    :param pause: 스크롤 간 대기 시간 (초)
    """
    last_count = 0
    stagnant_rounds = 0
    for i in range(max_scrolls):
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
        time.sleep(pause)
        items = driver.find_elements(By.CSS_SELECTOR, item_selector)
        cur_count = len(items)
        if cur_count == last_count:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
        last_count = cur_count
        print(f"스크롤 {i+1}회, 현재 아이템 수: {cur_count}")
        # 연속으로 3번 증가 없음 -> 바닥 도달로 판단
        if stagnant_rounds >= 3:
            print("더 이상 새로운 아이템이 로드되지 않습니다. 스크롤 종료.")
            break


def parse_duration_to_seconds(text: str) -> Optional[int]:
    if not text:
        return None
    t = re.sub(r"\s+", "", text).upper()
    if any(k in t for k in ["LIVE", "실시간", "스트리밍", "PREMIERE", "예정"]):
        return None
    # expected HH:MM:SS or MM:SS
    m = re.match(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$", t)
    if not m:
        return None
    h = int(m.group(1) or 0)
    m_ = int(m.group(2))
    s = int(m.group(3))
    return h * 3600 + m_ * 60 + s


def parse_korean_views(text: str) -> Optional[int]:
    """
    다양한 조회수 표기 문자열을 정수로 변환합니다.
    예: '조회수 1,234회', '조회수 2.3만회', '1.2천회', '1,234 views', '1.2K views', '2.3M views', 'No views'
    변환 실패 시 None 반환.
    """
    if not text:
        return None
    raw = text.strip()
    lower = raw.lower()

    # 명시적인 0 처리
    if any(k in lower for k in ["no views", "조회수 없음", "조회수없음"]):
        return 0

    # 공통 정리
    t = raw
    t = t.replace("조회수", "").replace("회", "").strip()
    t = re.sub(r"\s+", "", t)

    # 한국어 단위: 억, 만, 천
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)(억|만|천)?$", t)
    if m:
        num = float(m.group(1))
        unit = m.group(2)
        if unit == "억":
            num *= 100_000_000
        elif unit == "만":
            num *= 10_000
        elif unit == "천":
            num *= 1_000
        return int(num)

    # 영어 단위: K, M, B
    m_en = re.match(r"^([0-9]+(?:\.[0-9]+)?)([KMBkmb])?$", re.sub(r"[^0-9KMBkmb\.]", "", lower))
    if m_en:
        num = float(m_en.group(1))
        unit = (m_en.group(2) or '').upper()
        if unit == 'K':
            num *= 1_000
        elif unit == 'M':
            num *= 1_000_000
        elif unit == 'B':
            num *= 1_000_000_000
        return int(num)

    # 숫자만 추출 (쉼표 포함)
    m2 = re.search(r"([0-9][0-9,]*)", raw)
    if m2:
        return int(m2.group(1).replace(",", ""))

    return None


def extract_views_text_from_card(card) -> Optional[str]:
    """
    카드 요소에서 조회수 텍스트를 최대한 다양한 방법으로 추출합니다.
    반환 예: '조회수 1.2만회' 또는 '1,234 views'
    """
    # 1) 가장 흔한 메타데이터 라인
    try:
        spans = card.find_elements(By.CSS_SELECTOR, "#metadata-line span.inline-metadata-item")
        for sp in spans:
            txt = (sp.text or "").strip()
            if not txt:
                continue
            if ("조회수" in txt) or ("views" in txt.lower()):
                return txt
    except Exception:
        pass

    # 2) ytd-video-meta-block 내부의 형식
    try:
        spans = card.find_elements(By.CSS_SELECTOR, "ytd-video-meta-block span")
        for sp in spans:
            txt = (sp.text or "").strip()
            if ("조회수" in txt) or ("views" in txt.lower()):
                return txt
    except Exception:
        pass

    # 3) 썸네일 aria-label에서 파싱
    try:
        thumb = card.find_element(By.CSS_SELECTOR, "a#thumbnail")
        aria = thumb.get_attribute("aria-label") or ""
        m = re.search(r"(조회수\s*[^\s]+회|[0-9][0-9,\.]*\s+views)", aria, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    except Exception:
        pass

    # 4) 제목 링크의 aria-label에서 파싱
    try:
        tlink = card.find_element(By.CSS_SELECTOR, "a#video-title")
        aria = tlink.get_attribute("aria-label") or ""
        m = re.search(r"(조회수\s*[^\s]+회|[0-9][0-9,\.]*\s+views)", aria, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    except Exception:
        pass

    return None


def extract_duration_from_card(card) -> (Optional[str], Optional[int]):
    """
    카드에서 썸네일 오버레이에 표시되는 재생 길이 텍스트와 초 단위 값을 추출합니다.
    """
    selectors = [
        "ytd-thumbnail-overlay-time-status-renderer span#text",
        "#overlays ytd-thumbnail-overlay-time-status-renderer span#text",
        "ytd-thumbnail-overlay-time-status-renderer #text",
        "ytd-thumbnail-overlay-time-status-renderer",
    ]
    for sel in selectors:
        try:
            el = card.find_element(By.CSS_SELECTOR, sel)
            txt = (el.text or "").strip()
            txt = re.sub(r"\s+", " ", txt)
            # 유튜브는 종종 공백이 많은 문자열을 줌 → 공백 제거 후 파싱
            raw = re.sub(r"\s+", "", txt)
            seconds = parse_duration_to_seconds(raw)
            if seconds is not None:
                return raw, seconds
        except Exception:
            continue

    # aria-label에서 시간 포함시 추출
    try:
        thumb = card.find_element(By.CSS_SELECTOR, "a#thumbnail")
        aria = thumb.get_attribute("aria-label") or ""
        m = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)", aria)
        if m:
            raw = m.group(1)
            return raw, parse_duration_to_seconds(raw)
    except Exception:
        pass

    return None, None


def extract_title_and_url_from_card(card) -> Tuple[Optional[str], Optional[str], str]:
    """
    카드 요소에서 제목과 URL을 다양한 셀렉터로 추출합니다.
    반환: (title, url, method)
    method는 어떤 경로로 추출했는지 로그용 태그입니다.
    """
    # 1) a#video-title (가장 흔한 케이스)
    try:
        a = card.find_element(By.CSS_SELECTOR, "a#video-title")
        title = (a.get_attribute("title") or a.text or "").strip()
        href = a.get_attribute("href")
        if title:
            return title, href, "a#video-title"
    except Exception:
        pass

    # 2) yt-formatted-string#video-title 텍스트 + 썸네일 링크로 URL
    try:
        t = card.find_element(By.CSS_SELECTOR, "yt-formatted-string#video-title")
        title = (t.text or "").strip()
        href = None
        try:
            a = card.find_element(By.CSS_SELECTOR, "a#thumbnail")
            href = a.get_attribute("href")
        except Exception:
            # 아무 a 태그나 watch 링크
            try:
                a = card.find_element(By.CSS_SELECTOR, "a[href*='watch']")
                href = a.get_attribute("href")
            except Exception:
                pass
        if title:
            return title, href, "yt-formatted-string#video-title + thumbnail"
    except Exception:
        pass

    # 3) a#video-title-link (일부 레이아웃/검색)
    try:
        a = card.find_element(By.CSS_SELECTOR, "a#video-title-link")
        title = (a.get_attribute("title") or a.text or "").strip()
        href = a.get_attribute("href")
        if title:
            return title, href, "a#video-title-link"
    except Exception:
        pass

    # 4) 일반 헤더 내 링크
    try:
        a = card.find_element(By.CSS_SELECTOR, "h3 a")
        title = (a.get_attribute("title") or a.text or "").strip()
        href = a.get_attribute("href")
        if title:
            return title, href, "h3 a"
    except Exception:
        pass

    # 5) 썸네일 aria-label에서 제목 추정
    try:
        a = card.find_element(By.CSS_SELECTOR, "a#thumbnail")
        aria = (a.get_attribute("aria-label") or "").strip()
        # 보수적으로 앞부분을 제목으로 사용 (콤마/ by 앞)
        m = re.match(r"([^,|]+)", aria)
        title = (m.group(1).strip() if m else aria) or None
        href = a.get_attribute("href")
        if title:
            return title, href, "thumbnail aria-label"
    except Exception:
        pass

    return None, None, "not-found"


def wait_for(driver, by, value, timeout: int = 15):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))


def wait_click_xpath(driver, xpath: str, timeout: int = 15):
    el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
    el.click()
    return el


def try_dismiss_overlays(driver):
    """
    쿠키 동의/로그인 유도 등 클릭을 방해하는 오버레이를 닫습니다.
    실패해도 예외를 던지지 않습니다.
    """
    candidates = [
        # 쿠키 동의 (KR/EN 변형)
        "//button[.//span[contains(., '동의')]]",
        "//button[normalize-space()='동의함']",
        "//button[contains(., 'I agree')]",
        "//button[contains(., 'Accept all')]",
        # 로그인 유도 닫기 X
        "//button[@aria-label='닫기' or @aria-label='Close']",
    ]
    for xp in candidates:
        try:
            el = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            print(f"오버레이를 닫았습니다: {xp}")
        except Exception:
            pass


def nav_to_videos_tab(driver):
    """
    채널 페이지에서 '동영상/VIDEOS' 탭으로 이동합니다.
    다양한 UI에 대응하고, 실패 시 /videos로 직접 이동합니다.
    """
    print("'동영상' 탭으로 이동을 시도합니다.")
    try_dismiss_overlays(driver)
    # 여러 UI 패턴 시도
    tab_xpaths = [
        "//div[@id='tabsContent']//a[contains(@href, '/videos')]",
        "//tp-yt-paper-tab[.//div[contains(., '동영상')]]",
        "//tp-yt-paper-tab[.//div[contains(., 'Videos')]]",
        "//yt-tab-shape//div[contains(., '동영상')]/ancestor::yt-tab-shape",
        "//yt-tab-shape//div[contains(., 'Videos')]/ancestor::yt-tab-shape",
        "//*[@role='tab' and (contains(., '동영상') or contains(., 'Videos'))]",
    ]
    for idx, xp in enumerate(tab_xpaths, 1):
        try:
            print(f"- 탭 선택자 시도 {idx}")
            el = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            print("탭 클릭 성공. 동영상 그리드 대기.")
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.TAG_NAME, "ytd-rich-grid-renderer"))
            )
            return True
        except Exception:
            print(f"  탭 선택자 {idx} 실패")

    # 클릭 실패 → URL로 직접 이동
    cur = driver.current_url
    print("탭 클릭 실패. /videos로 직접 이동을 시도합니다.")
    base = re.sub(r"/(featured|videos|playlists|community|channels|about).*$", "", cur)
    # 핸들/채널 경로가 없는 경우, 상위 경로 처리
    if not re.search(r"/(channel/|/@)", base):
        base = cur.split("?")[0].rstrip("/")
    target = base.rstrip("/") + "/videos"
    print(f"직접 이동 URL: {target}")
    driver.get(target)
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.TAG_NAME, "ytd-rich-grid-renderer"))
        )
        print("동영상 그리드 감지 성공.")
        return True
    except Exception:
        print("동영상 그리드 감지 실패. UI 변경 가능성.")
        return False


def scrape_channel_and_play_lowest(channel_name: str, save_csv: bool = False, play_seconds: int = 20, close_on_finish: bool = True) -> List[Dict]:
    """
    1) 유튜브 접속 → 채널명 검색
    2) 해당 채널로 이동 후 '동영상' 탭 진입
    3) 모든 동영상의 제목/조회수/URL 수집
    4) 조회수 가장 낮은 동영상을 클릭하여 재생
    5) 수집 데이터 반환, 옵션으로 CSV 저장
    """
    print("브라우저를 초기화합니다 (undetected-chromedriver)...")
    driver = uc.Chrome()

    try:
        # 1) 유튜브 메인 접속 후 검색
        print("1) 유튜브 메인 페이지로 이동합니다.")
        driver.get("https://www.youtube.com/")
        print("검색창 표시를 대기합니다.")
        wait_for(driver, By.NAME, "search_query")
        print(f"검색어 입력: '{channel_name}'")
        search_box = driver.find_element(By.NAME, "search_query")
        search_box.clear()
        search_box.send_keys(channel_name)
        print("엔터를 눌러 검색을 실행합니다.")
        search_box.send_keys(Keys.ENTER)

        # 검색 결과 로드 대기
        print("검색 결과 로드를 대기합니다.")
        wait_for(driver, By.TAG_NAME, "ytd-search")
        time.sleep(1.5)
        print("검색 결과가 표시되었습니다.")

        # 2) 채널 결과 클릭 시도 (여러 UI 케이스 대응)
        channel_clicked = False
        xpaths = [
            # 최신 UI: 채널 카드
            f"//ytd-channel-renderer//a[@id='main-link' and .//span[normalize-space()='{channel_name}']]",
            # 대체: 텍스트만으로 매칭되는 링크
            f"//a[@id='main-link']//span[normalize-space()='{channel_name}']/ancestor::a[@id='main-link']",
            # 채널 썸네일 링크
            f"//ytd-channel-renderer//a[@id='avatar-link' or @id='img' or @id='main-link']"
        ]
        print("채널 링크를 찾고 클릭을 시도합니다.")
        for idx, xp in enumerate(xpaths, 1):
            try:
                print(f"- 후보 {idx} XPath 시도")
                el = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xp)))
                # 정확한 채널명 검증
                if channel_name.strip() in el.text or "channel" in (el.get_attribute("href") or "") or "/@" in (el.get_attribute("href") or ""):
                    print("채널 링크를 클릭합니다.")
                    el.click()
                    channel_clicked = True
                    break
            except Exception:
                print(f"  후보 {idx} 매칭 실패")
                continue
        if not channel_clicked:
            raise RuntimeError("채널 링크를 찾을 수 없습니다. 검색 결과 UI가 변경되었을 수 있습니다.")

        # 채널 페이지 로드 대기
        print("채널 페이지 로드를 대기합니다.")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "tabsContent")))
        time.sleep(1)
        print("채널 페이지가 로드되었습니다.")

        # 3) '동영상' 탭으로 이동
        ok = nav_to_videos_tab(driver)
        if not ok:
            raise RuntimeError("동영상 탭으로 이동하지 못했습니다. 스크립트를 최신 UI에 맞게 업데이트하세요.")
        time.sleep(1.0)

        # 4) 스크롤하여 모든 동영상 로드 시도
        print("모든 동영상을 로드하기 위해 스크롤을 시작합니다.")
        smart_scroll_until_no_new(driver, "ytd-rich-grid-media", max_scrolls=40, pause=1.2)
        print("스크롤을 종료합니다.")

        print("영상 정보 수집을 시작합니다.")
        cards = driver.find_elements(By.CSS_SELECTOR, "ytd-rich-grid-media")
        print(f"감지된 카드 수: {len(cards)}")

        scraped: List[Dict] = []
        for idx, card in enumerate(cards, 1):
            try:
                # 카드 가시화 → 지연 로딩된 메타데이터를 유도
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
                    time.sleep(0.25)
                except Exception:
                    pass

                title, href, tmethod = extract_title_and_url_from_card(card)

                # 조회수 텍스트 다양한 방식으로 추출
                views_text = extract_views_text_from_card(card)
                if views_text is None:
                    print(f"  · [{idx}] 조회수 텍스트를 찾지 못했습니다. 다른 형식일 수 있습니다.")

                # 길이 추출
                duration_str, duration_sec = extract_duration_from_card(card)
                if duration_sec is None:
                    print(f"  · [{idx}] 재생 길이 추출 실패 → 기본값 미설정")

                # 숫자 변환 (한글/영문 혼합 처리)
                vt = views_text or ""
                if "views" in vt.lower() and "조회수" not in vt:
                    # '1,234 views' → 숫자만 추출 후 한국어 포맷으로 위임
                    mnum = re.search(r"([0-9][0-9,\.]*)\s*[KMBkmb]?", vt)
                    if mnum:
                        vt = mnum.group(1)
                views_val = parse_korean_views(vt)
                if title and (views_val is not None):
                    scraped.append({"index": idx, "title": title, "views": views_val, "url": href, "duration": duration_str, "duration_seconds": duration_sec})
                    url_msg = href if href else "URL 없음"
                    dmsg = duration_str if duration_str else "길이 없음"
                    print(f"- [{idx}] 제목: {title} | 조회수: {views_val:,} | 길이: {dmsg} | {tmethod} | {url_msg}")
                else:
                    if not title:
                        print(f"- [{idx}] 카드 파싱 불완전: 제목 추출 실패 (method={tmethod})")
                    elif views_text:
                        print(f"- [{idx}] 카드 파싱 불완전: 원본 조회수 텍스트='{views_text}' → 변환 실패")
                    else:
                        print(f"- [{idx}] 카드 파싱 불완전 (title/url/views 누락)")
            except Exception as e:
                print(f"- [{idx}] 카드 파싱 오류: {e}")

        print(f"총 {len(scraped)}개의 영상 정보를 수집했습니다.")

        # 5) 조회수 최저 영상 찾기 및 재생
        if not scraped:
            print("수집된 영상이 없습니다.")
            return []

        lowest = min(scraped, key=lambda x: x["views"])
        print(f"최저 조회수 영상: {lowest['title']} ({lowest['views']:,}회)")
        try:
            # 이미 로드된 카드 중 해당 제목과 일치하는 항목 클릭 시도
            target_xpath = f"//ytd-rich-grid-media//a[@id='video-title' and normalize-space()='{lowest['title']}']"
            print("그리드 내에서 해당 영상을 클릭 시도합니다.")
            el = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, target_xpath)))
            el.click()
        except Exception:
            # URL 직접 이동
            print("그리드 클릭 실패 → URL로 직접 이동합니다.")
            driver.get(lowest["url"])

        print("영상 재생 페이지로 이동했습니다. 플레이어 표시를 확인합니다.")
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#movie_player, video"))
            )
            print("플레이어가 표시되었습니다. 재생이 시작되었는지 확인하세요.")
        except Exception:
            print("플레이어 감지 실패 (UI 변경 또는 로딩 지연 가능)")

        # 재생 시간을 확보하기 위해 대기
        if play_seconds and play_seconds > 0:
            cap = 300
            eff = min(int(play_seconds), cap)
            if eff < int(play_seconds):
                print(f"요청된 재생 대기 {play_seconds}초를 {cap}초로 제한합니다.")
            print(f"영상을 {eff}초 동안 재생하도록 대기합니다.")
            time.sleep(eff)

        # 종료 보류: close_on_finish=False인 경우 브라우저 유지
        if not close_on_finish:
            print("브라우저를 계속 열어둡니다. 종료하려면 Ctrl+C로 중단하세요.")
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                print("사용자 요청으로 종료를 진행합니다.")

        # 선택적으로 CSV 저장
        if save_csv:
            try:
                df = pd.DataFrame(scraped)
                saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                df["saved_at"] = saved_at
                df_sorted = df.sort_values(by="views", ascending=True)
                df_sorted.to_csv("youtube_channel_videos.csv", index=False, encoding="utf-8-sig")
                print("'youtube_channel_videos.csv' 파일로 저장 완료.")
            except Exception as e:
                print(f"CSV 저장 중 오류: {e}")

        return scraped

    finally:
        # 모든 작업이 끝나면 드라이버 종료 (옵션)
        if close_on_finish:
            print("드라이버를 종료합니다.")
            driver.quit()


def collect_channel_videos(driver, channel_name: str) -> List[Dict]:
    print(f"채널 '{channel_name}'의 모든 동영상 정보를 수집합니다.")
    # 채널로 이동하여 동영상 탭 표시
    print("채널 이동 및 동영상 탭 로드 중...")
    # 재사용: 검색 → 채널 클릭 → 동영상 탭 이동
    # 아래는 scrape_channel_and_play_lowest와 유사한 흐름이므로 간단화하여 호출
    # 1) 메인 이동 → 검색
    driver.get("https://www.youtube.com/")
    wait_for(driver, By.NAME, "search_query")
    sb = driver.find_element(By.NAME, "search_query")
    sb.clear()
    sb.send_keys(channel_name)
    sb.send_keys(Keys.ENTER)
    wait_for(driver, By.TAG_NAME, "ytd-search")
    time.sleep(1)
    # 채널 클릭 시도 (간단 버전)
    try:
        el = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.XPATH, f"//ytd-channel-renderer//a[@id='main-link' and .//span[normalize-space()='{channel_name}']]")))
        el.click()
    except Exception:
        # 대체 케이스
        el = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.XPATH, "//ytd-channel-renderer//a[@id='main-link']")))
        el.click()
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "tabsContent")))
    ok = nav_to_videos_tab(driver)
    if not ok:
        raise RuntimeError("동영상 탭 로드 실패")
    time.sleep(1)

    # 모든 동영상이 로드될 때까지 스마트 스크롤
    print("모든 동영상을 로드하기 위해 스크롤을 시작합니다.")
    smart_scroll_until_no_new(driver, "ytd-rich-grid-media", max_scrolls=100, pause=1.0)
    cards = driver.find_elements(By.CSS_SELECTOR, "ytd-rich-grid-media")
    print(f"수집 대상 카드 수: {len(cards)}")
    results: List[Dict] = []
    for idx, card in enumerate(cards, 1):
        try:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
                time.sleep(0.15)
            except Exception:
                pass
            title, href, tmethod = extract_title_and_url_from_card(card)
            vtxt = extract_views_text_from_card(card)
            vt = vtxt or ""
            if "views" in vt.lower() and "조회수" not in vt:
                mnum = re.search(r"([0-9][0-9,\.]*)\s*[KMBkmb]?", vt)
                if mnum:
                    vt = mnum.group(1)
            views = parse_korean_views(vt)
            dstr, dsec = extract_duration_from_card(card)
            results.append({
                "index": idx,
                "title": title or "",
                "views": int(views) if views is not None else None,
                "url": href,
                "duration": dstr,
                "duration_seconds": dsec,
            })
            print(f"- [{idx}] {title} | 조회수: {views} | 길이: {dstr} | {tmethod}")
        except Exception as e:
            print(f"카드 수집 실패 [{idx}]: {e}")
    return results


def play_videos_sequence(driver, videos: List[Dict], base_videos_url: Optional[str] = None):
    print("1번부터 순서대로 영상을 재생합니다.")
    for v in sorted(videos, key=lambda x: x.get("index", 0)):
        title = v.get("title") or "(제목 없음)"
        url = v.get("url")
        dsec = v.get("duration_seconds")
        if not dsec:
            print(f"- [{v.get('index')}] {title}: 길이 정보 없음 → 30초 기본 대기")
            dsec = 30
        print(f"- [{v.get('index')}] '{title}' 재생 (예상 {dsec}초)")
        try:
            if url:
                driver.get(url)
            elif base_videos_url:
                # 그리드에서 제목으로 클릭 시도
                driver.get(base_videos_url)
                try:
                    xp = f"//ytd-rich-grid-media//a[@id='video-title' and normalize-space()='{title}']"
                    el = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.XPATH, xp)))
                    el.click()
                except Exception:
                    print("  · 제목 클릭 실패, 다음 영상으로 진행")
                    continue
            else:
                print("  · URL/기준 페이지가 없어 건너뜀")
                continue

            WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#movie_player, video")))
            # +2초 버퍼를 둡니다.
            # 영상 재생 대기는 최대 5분(300초)로 제한
            cap = 300
            wait_time = int(dsec) + 2
            eff = min(wait_time, cap)
            if eff < wait_time:
                print(f"  · 원래 대기 {wait_time}초 → 5분 제한 적용: {eff}초")
            else:
                print(f"  · 재생 대기 {eff}초...")
            time.sleep(eff)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"  · 재생 중 오류: {e}")


def run_loop(channel_name: str, csv_path: str = "youtube_channel_videos.csv"):
    # 브라우저 옵션 설정(배경 스로틀링 완화, 창 크기 고정)
    print("브라우저를 초기화합니다 (지속 실행 모드)...")
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1600,1000")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-renderer-backgrounding")
    driver = uc.Chrome(options=options)

    try:
        try:
            df = pd.read_csv(csv_path)
            print(f"기존 CSV '{csv_path}'를 불러왔습니다. 행 수: {len(df)}")
        except FileNotFoundError:
            print(f"CSV '{csv_path}'가 없습니다. 먼저 정보 수집을 진행합니다.")
            vids = collect_channel_videos(driver, channel_name)
            saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df = pd.DataFrame(vids)
            df["saved_at"] = saved_at
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"초기 수집 CSV 저장 완료: {csv_path}")

        print("무한 반복 재생 루프를 시작합니다. (Ctrl+C로 종료)")
        while True:
            # 매 라운드 시작 시 최신 목록 전체 재수집 → 신규 업로드 자동 반영
            vids = collect_channel_videos(driver, channel_name)
            saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df = pd.DataFrame(vids)
            df["saved_at"] = saved_at
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"CSV 업데이트 완료(재수집): {csv_path} | 총 {len(df)}개")

            base_videos_url = driver.current_url
            videos = df.to_dict(orient="records")
            print(f"이번 라운드 재생 대상: {len(videos)}개 (1번부터 순서대로)")
            play_videos_sequence(driver, videos, base_videos_url=base_videos_url)

            # 라운드 종료 후 저장 시간 갱신
            saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df["saved_at"] = saved_at
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"CSV 업데이트 완료(라운드 완료): {csv_path}")

    except KeyboardInterrupt:
        print("사용자 인터럽트 감지. 종료합니다.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    # 무한 반복: CSV 없으면 수집 후 모든 영상 순차 재생, 라운드마다 CSV 갱신
    CHANNEL_NAME = "조선대학교 SW중심사업단"
    run_loop(CHANNEL_NAME, csv_path="youtube_channel_videos.csv")
