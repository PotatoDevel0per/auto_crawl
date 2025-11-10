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


def collect_kakaotv_videos(driver, channel_name: str, channel_url: Optional[str] = None) -> List[Dict]:
    print(f"KakaoTV 채널 '{channel_name}'의 모든 동영상 정보를 수집합니다.")

    # 1) 채널 URL로 직접 이동
    if channel_url:
        print(f"지정된 채널 URL로 이동: {channel_url}")
        # /video 경로로 직접 이동하여 전체 동영상 목록 로드
        if "/video" not in channel_url:
            channel_url = channel_url.rstrip("/") + "/video"
        driver.get(channel_url)
    else:
        # 검색을 통한 채널 찾기
        base = "https://tv.kakao.com/"
        driver.get(base)
        try_dismiss_overlays(driver)

        # 검색창 찾기
        search_sel = [
            (By.CSS_SELECTOR, "input[type='text']"),
            (By.CSS_SELECTOR, "input[type='search']"),
            (By.CSS_SELECTOR, "input#searchKeyword"),
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
            raise RuntimeError("KakaoTV 검색창을 찾지 못했습니다.")

        print(f"검색어 입력: '{channel_name}'")
        sb.clear()
        sb.send_keys(channel_name)
        sb.send_keys(Keys.ENTER)
        time.sleep(2)
        try_dismiss_overlays(driver)

        # 채널 링크 찾기 (더 넓은 범위로 검색)
        print("검색 결과에서 채널 링크를 찾습니다...")
        time.sleep(2)  # 검색 결과 로딩 대기

        # 페이지 스크롤하여 결과 로드
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(1)

        # 모든 채널 링크 수집
        channel_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/channel']")
        print(f"찾은 채널 링크 수: {len(channel_links)}")

        channel_clicked = False
        for idx, link in enumerate(channel_links):
            try:
                href = link.get_attribute("href") or ""
                text = link.text.strip()
                print(f"  [{idx+1}] {text[:50]} - {href}")

                # 채널 이름이 포함되어 있거나, 첫 번째 채널 링크 사용
                if channel_name in text or idx == 0:
                    if href.startswith("/"):
                        href = "https://tv.kakao.com" + href

                    # 채널 ID 추출
                    m = re.search(r'/channel/(\d+)', href)
                    if m:
                        channel_id = m.group(1)
                        video_url = f"https://tv.kakao.com/channel/{channel_id}/video"
                        print(f"\n선택된 채널: {text[:50]}")
                        print(f"채널 전체 동영상 페이지로 이동: {video_url}")
                        driver.get(video_url)
                        channel_clicked = True
                        break
            except Exception as e:
                print(f"  링크 처리 중 오류: {e}")
                continue

        if not channel_clicked:
            print("\n검색 결과에서 채널을 찾지 못했습니다.")
            print("현재 페이지 URL:", driver.current_url)
            print("\n해결 방법:")
            print("1. 카카오TV에서 수동으로 채널을 찾아 URL을 확인하세요.")
            print("2. kakao_auto_crawl.py 파일의 KAKAO_CHANNEL_URL 변수에 채널 URL을 설정하세요.")
            print("   예: KAKAO_CHANNEL_URL = 'https://tv.kakao.com/channel/XXXXX'")
            raise RuntimeError("채널을 찾지 못했습니다. channel_url을 직접 지정해주세요.")

    time.sleep(2)
    try_dismiss_overlays(driver)

    # 2) 더보기 버튼 클릭으로 모든 영상 로드
    print("더보기 버튼을 클릭하여 모든 영상을 로드합니다.")
    more_clicks = 0
    while more_clicks < 100:  # 최대 100회
        try:
            # 페이지 하단으로 스크롤
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            # 더보기 버튼 찾기
            more_button = None
            more_selectors = [
                "//a[contains(text(), '더보기')]",
                "//button[contains(text(), '더보기')]",
                "//a[contains(@class, 'more')]",
                "//button[contains(@class, 'more')]",
            ]
            for sel in more_selectors:
                try:
                    more_button = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, sel))
                    )
                    break
                except Exception:
                    continue

            if more_button:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", more_button)
                time.sleep(0.3)
                more_button.click()
                more_clicks += 1
                print(f"더보기 클릭 #{more_clicks}")
                time.sleep(1)
            else:
                print("더보기 버튼을 찾지 못했습니다. 로딩 완료.")
                break
        except Exception:
            print("더 이상 더보기 버튼이 없습니다.")
            break

    # 3) 추가 스크롤로 동적 로딩 확인
    smart_scroll_until_no_new(driver, "a.link_contents, a[href*='/cliplink/']", max_scrolls=30, pause=1.0)

    # 4) 영상 링크 수집
    print("영상 정보를 수집합니다.")
    cards = driver.find_elements(By.CSS_SELECTOR, "a.link_contents, a[href*='/cliplink/']")
    print(f"감지된 영상 카드 수: {len(cards)}")

    out: List[Dict] = []
    seen_urls = set()

    for idx, a in enumerate(cards, 1):
        try:
            href = a.get_attribute("href")
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)

            # URL 정규화
            if href.startswith("/"):
                href = "https://tv.kakao.com" + href

            # cliplink가 포함된 영상만 수집
            if "/cliplink/" not in href:
                continue

            # 제목 추출
            title = (a.get_attribute("title") or "").strip()
            if not title:
                try:
                    # aria-label에서 추출
                    title = (a.get_attribute("aria-label") or "").strip()
                except Exception:
                    pass
            if not title:
                try:
                    # 텍스트에서 추출
                    title = (a.text or "").strip()
                except Exception:
                    pass

            # 컨테이너 찾기
            try:
                container = a.find_element(By.XPATH, "ancestor::li[1]")
            except Exception:
                try:
                    container = a.find_element(By.XPATH, "ancestor::div[1]")
                except Exception:
                    container = a

            # 재생 시간 추출
            duration_text = None
            try:
                duration_elem = container.find_element(By.CSS_SELECTOR, ".txt_time, [class*='time']")
                duration_text = duration_elem.text.strip()
            except Exception:
                try:
                    texts = [e.text for e in container.find_elements(By.TAG_NAME, "span")]
                    for t in texts:
                        if re.search(r'\d{1,2}:\d{2}', t):
                            duration_text = t.strip()
                            break
                except Exception:
                    pass

            duration_seconds = parse_duration_to_seconds(duration_text) if duration_text else None

            # 조회수 추출
            views_val = None
            try:
                view_elem = container.find_element(By.CSS_SELECTOR, ".txt_view, [class*='view']")
                views_text = view_elem.text.strip()
                views_val = parse_views_generic(views_text)
            except Exception:
                try:
                    texts = [e.text for e in container.find_elements(By.TAG_NAME, "span")]
                    for t in texts:
                        if any(k in t for k in ["재생", "조회", "views"]):
                            views_val = parse_views_generic(t)
                            if views_val is not None:
                                break
                except Exception:
                    pass

            out.append({
                "index": len(out) + 1,
                "title": title or "(제목 없음)",
                "views": views_val,
                "url": href,
                "duration": duration_text,
                "duration_seconds": duration_seconds,
            })
            print(f"- [{len(out)}] {title} | 조회수: {views_val} | 길이: {duration_text}")

        except Exception as e:
            print(f"카드 파싱 실패: {e}")
            continue

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

            # 오버레이 및 팝업 닫기
            try_dismiss_overlays(driver)

            # 재생 버튼 클릭 (카카오TV는 자동 재생이 안 되므로 필수)
            try:
                print("  · 재생 버튼을 찾는 중...")
                play_button_selectors = [
                    "//button[contains(@class, 'btn_play')]",
                    "//button[contains(@class, 'play')]",
                    "//button[@aria-label='재생' or @aria-label='play']",
                    "//button[contains(@title, '재생')]",
                    "//div[contains(@class, 'play')]//button",
                ]

                play_clicked = False
                for selector in play_button_selectors:
                    try:
                        play_btn = WebDriverWait(driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        play_btn.click()
                        print("  · 재생 버튼 클릭 완료")
                        play_clicked = True
                        time.sleep(1)
                        break
                    except Exception:
                        continue

                # 재생 버튼을 못 찾으면 video 태그에 직접 재생 명령
                if not play_clicked:
                    print("  · 재생 버튼을 찾지 못함. JavaScript로 직접 재생 시도...")
                    try:
                        driver.execute_script("""
                            var videos = document.querySelectorAll('video');
                            for (var i = 0; i < videos.length; i++) {
                                videos[i].play();
                            }
                        """)
                        print("  · JavaScript로 재생 시작")
                    except Exception as js_err:
                        print(f"  · JavaScript 재생 실패: {js_err}")

            except Exception as play_err:
                print(f"  · 재생 버튼 클릭 실패: {play_err}")

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


def run_loop_kakaotv(channel_name: str, csv_path: str = "kakaotv_videos.csv", channel_url: Optional[str] = None):
    print("KakaoTV 무한 재생 루프 시작")
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1600,1000")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-renderer-backgrounding")
    driver = uc.Chrome(options=options)
    try:
        while True:
            vids = collect_kakaotv_videos(driver, channel_name, channel_url=channel_url)
            saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df = pd.DataFrame(vids)
            df["saved_at"] = saved_at
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"CSV 업데이트(KakaoTV): {csv_path} | {len(df)}개")
            play_videos_sequence_generic(driver, vids, site="KakaoTV")
    except KeyboardInterrupt:
        print("사용자 인터럽트(KakaoTV). 종료합니다.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    CHANNEL_NAME = "조선대학교 SW중심사업단"
    # 필요하다면 채널 URL을 직접 지정하세요 (예: "https://tv.kakao.com/channel/XXXX")
    KAKAO_CHANNEL_URL = "https://tv.kakao.com/channel/10114190/video"
    run_loop_kakaotv(CHANNEL_NAME, channel_url=KAKAO_CHANNEL_URL)
