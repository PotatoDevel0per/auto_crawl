import time
from datetime import datetime
import re
from typing import List, Dict, Optional

import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def smart_scroll_until_no_new(driver, item_selector: str, max_scrolls: int = 80, pause: float = 1.0):
    last = 0
    still = 0
    for i in range(max_scrolls):
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
        time.sleep(pause)
        cnt = len(driver.find_elements(By.CSS_SELECTOR, item_selector))
        print(f"스크롤 {i+1}회, 항목 수 {cnt}")
        if cnt == last:
            still += 1
        else:
            still = 0
        last = cnt
        if still >= 3:
            print("더 이상 아이템 증가 없음. 스크롤 종료.")
            break


def parse_duration_to_seconds(text: str) -> Optional[int]:
    if not text:
        return None
    t = re.sub(r"\s+", "", text).upper()
    if any(k in t for k in ["LIVE", "실시간", "스트리밍", "PREMIERE", "예정"]):
        return None
    m = re.match(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$", t)
    if not m:
        return None
    h = int(m.group(1) or 0)
    m_ = int(m.group(2))
    s = int(m.group(3))
    return h * 3600 + m_ * 60 + s


def parse_korean_views(text: str) -> Optional[int]:
    if not text:
        return None
    raw = text.strip()
    lower = raw.lower()
    if any(k in lower for k in ["no views", "조회수 없음", "조회수없음"]):
        return 0
    t = raw.replace("조회수", "").replace("조회", "").replace("재생", "").replace("회", "")
    t = re.sub(r"\s+", "", t)
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
    m2 = re.search(r"([0-9][0-9,]*)", raw)
    if m2:
        return int(m2.group(1).replace(",", ""))
    return None


def parse_views_generic(text: str) -> Optional[int]:
    if not text:
        return None
    t = text.strip()
    t_clean = re.sub(r"(조회수|조회|재생수|재생|views|view)", "", t, flags=re.IGNORECASE)
    t_clean = t_clean.replace("회", "").strip()
    v = parse_korean_views(t_clean)
    if v is not None:
        return v
    m = re.search(r"([0-9][0-9,]*)", t)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def try_dismiss_overlays(driver):
    candidates = [
        "//button[.//span[contains(., '동의')]]",
        "//button[normalize-space()='동의함']",
        "//button[contains(., 'I agree')]",
        "//button[contains(., 'Accept all')]",
        "//button[@aria-label='닫기' or @aria-label='Close']",
    ]
    for xp in candidates:
        try:
            el = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            print(f"오버레이 닫힘: {xp}")
        except Exception:
            pass


def collect_navertv_videos(driver, channel_name: str) -> List[Dict]:
    print(f"NaverTV 채널 '{channel_name}'의 모든 동영상 정보를 수집합니다.")
    base = "https://tv.naver.com/"
    driver.get(base)
    try_dismiss_overlays(driver)
    # 검색
    search_sel = [
        (By.CSS_SELECTOR, "input[type='search']"),
        (By.CSS_SELECTOR, "input#search_input"),
        (By.CSS_SELECTOR, "input#search_keyword"),
        (By.CSS_SELECTOR, "input[name='query']"),
        (By.CSS_SELECTOR, "input[placeholder*='검색']"),
    ]
    sb = None
    for by, sel in search_sel:
        try:
            sb = WebDriverWait(driver, 5).until(EC.presence_of_element_located((by, sel)))
            break
        except Exception:
            continue
    if not sb:
        raise RuntimeError("NaverTV 검색창을 찾지 못했습니다.")
    sb.clear(); sb.send_keys(channel_name); sb.send_keys(Keys.ENTER)
    time.sleep(2)
    try_dismiss_overlays(driver)

    # 채널 클릭 시도
    channel_xps = [
        f"//a[contains(@href,'/channel') and .//*[contains(normalize-space(), '{channel_name}')]]",
        f"//a[contains(@href,'/channel') and contains(normalize-space(), '{channel_name}')]",
        f"//a[contains(@href,'/list') and .//*[contains(normalize-space(), '{channel_name}')]]",
    ]
    for xp in channel_xps:
        try:
            el = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click(); break
        except Exception:
            continue

    time.sleep(1)
    smart_scroll_until_no_new(driver, "a[href*='/v/']", max_scrolls=80, pause=1.0)
    cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='/v/']")
    print(f"감지된 영상 수: {len(cards)}")
    out: List[Dict] = []
    for idx, a in enumerate(cards, 1):
        try:
            title = (a.get_attribute("title") or a.text or "").strip()
            href = a.get_attribute("href")
            try:
                container = a.find_element(By.XPATH, "ancestor::*[self::li or self::div][1]")
            except Exception:
                container = a
            duration_text = None
            try:
                texts = [e.text for e in container.find_elements(By.XPATH, ".//*[self::span or self::em][contains(.,':')]")]
                for t in texts:
                    m = re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", t)
                    if m:
                        duration_text = m.group(0); break
            except Exception:
                pass
            duration_seconds = parse_duration_to_seconds(duration_text) if duration_text else None
            views_val = None
            try:
                texts = [e.text for e in container.find_elements(By.XPATH, ".//*[self::span or self::em or self::div]")]
                cand = None
                for t in texts:
                    if any(k in t for k in ["조회", "재생", "views", "VIEW", "View"]):
                        cand = t; break
                views_val = parse_views_generic(cand) if cand else None
            except Exception:
                pass
            out.append({
                "index": idx, "title": title, "views": views_val, "url": href,
                "duration": duration_text, "duration_seconds": duration_seconds,
            })
            print(f"- [{idx}] {title} | 조회수: {views_val} | 길이: {duration_text}")
        except Exception as e:
            print(f"카드 파싱 실패 [{idx}]: {e}")
    return out


def play_videos_sequence_generic(driver, videos: List[Dict], site: str):
    print(f"{site}: 순서대로 영상 재생 시작")
    for v in sorted(videos, key=lambda x: x.get("index", 0)):
        title = v.get("title") or "(제목 없음)"
        url = v.get("url")
        dsec = v.get("duration_seconds") or 30
        print(f"- [{v.get('index')}] '{title}' 재생 ({dsec}초)")
        if not url:
            print("  · URL 없음 → 건너뜀")
            continue
        try:
            driver.get(url)
            try:
                WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, "video")))
            except Exception:
                pass
            # 최대 5분(300초) 제한
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


def run_loop_navertv(channel_name: str, csv_path: str = "navertv_videos.csv"):
    print("NaverTV 무한 재생 루프 시작")
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1600,1000")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-renderer-backgrounding")
    driver = uc.Chrome(options=options)
    try:
        while True:
            vids = collect_navertv_videos(driver, channel_name)
            saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df = pd.DataFrame(vids)
            df["saved_at"] = saved_at
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"CSV 업데이트(NaverTV): {csv_path} | {len(df)}개")
            play_videos_sequence_generic(driver, vids, site="NaverTV")
    except KeyboardInterrupt:
        print("사용자 인터럽트(NaverTV). 종료합니다.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    CHANNEL_NAME = "조선대학교 SW중심사업단"
    run_loop_navertv(CHANNEL_NAME)
