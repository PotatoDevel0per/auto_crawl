# YoutubCrawling (YouTube/KakaoTV/NaverTV Auto Crawler)

작성일: 2025-10-24  
작성자: PotatoDevel0per

## 목적
- 특정 채널/계정의 동영상 목록을 자동으로 수집하고(title, views, duration, url), CSV로 저장합니다.
- 각 플랫폼(YouTube, KakaoTV, NaverTV)별로 페이지를 스크롤하여 모든 영상을 수집합니다.
- 수집된 목록을 1번부터 순서대로 자동 재생하고, 라운드 종료 시 CSV를 갱신한 뒤 무한 반복합니다. (Ctrl+C로 종료)
- 모든 플랫폼에서 개별 영상 재생 대기는 최대 5분(300초)으로 제한됩니다.

## 주요 기능
- 플랫폼별 전용 스크립트 제공
  - YouTube: `youtube_auto_crawl.py`
  - KakaoTV: `kakao_auto_crawl.py`
  - NaverTV: `naver_auto_crawl.py`
- 수집 컬럼
  - index(1..N), title, views(정수), url, duration(원문), duration_seconds(초), saved_at(저장 시각)
- 조회수/길이 파싱
  - 조회수: 한국어(억/만/천, “조회수 …회”), 영어(K/M/B, “…, views”) 모두 지원
  - 길이: `HH:MM:SS` 또는 `MM:SS` 인식 (LIVE/예정 등은 길이 미확정 → 기본 30초 대기)
- 안정성 향상
  - 다양한 UI/레이아웃 대응 셀렉터, 무한 스크롤 로딩 감지, 오버레이(쿠키/로그인) 닫기 시도
  - 브라우저 백그라운드 스로틀링 완화 옵션 적용 및 고정 창 크기

## 요구 사항
- Python 3.9+
- Google Chrome(또는 Chromium) 설치
- Python 패키지
  - selenium
  - undetected-chromedriver
  - pandas

설치 예시
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install selenium undetected-chromedriver pandas
```

## 사용법
각 스크립트의 하단 `CHANNEL_NAME` 값을 원하는 채널/계정명으로 수정한 뒤 실행합니다. (현재 기본값: "조선대학교 SW중심사업단")

### YouTube
- 파일: `youtube_auto_crawl.py`
- 실행: `python youtube_auto_crawl.py`
- 동작:
  - 채널 검색 → 동영상 탭 이동 → 전체 목록 재수집 → `youtube_channel_videos.csv` 저장 → 1→N 자동 재생 → 라운드 종료 시 `saved_at` 갱신 → 반복

### KakaoTV
- 파일: `kakao_auto_crawl.py`
- 실행: `python kakao_auto_crawl.py`
- 동작:
  - 채널 검색 → 전체 목록 재수집 → `kakaotv_videos.csv` 저장 → 1→N 자동 재생 → 라운드 종료 시 `saved_at` 갱신 → 반복

### NaverTV
- 파일: `naver_auto_crawl.py`
- 실행: `python naver_auto_crawl.py`
- 동작:
  - 채널 검색 → 전체 목록 재수집 → `navertv_videos.csv` 저장 → 1→N 자동 재생 → 라운드 종료 시 `saved_at` 갱신 → 반복

## CSV 스키마
- 공통 컬럼: `index, title, views, url, duration, duration_seconds, saved_at`
- 비고
  - `views`는 정수(조회수 파싱 실패 시 빈 값일 수 있음)
  - `duration_seconds` 미확정(LIVE/예정 등) 시 기본 30초로 재생 대기
  - `saved_at`은 라운드별 갱신

## 팁 및 주의사항
- 창 크기/최소화
  - 창을 최소화하거나 지나치게 작게 만들면 레이아웃 변경/타이머 스로틀링이 발생할 수 있습니다.
  - 스크립트가 백그라운드 스로틀링 완화 옵션을 적용하지만, 가능하면 창 크기를 유지하는 것을 권장합니다.
- 팝업/오버레이
  - 쿠키 동의, 로그인 유도 팝업이 뜨는 경우 자동으로 닫기를 시도합니다. 간혹 수동으로 한 번 닫아야 할 수도 있습니다.
- 성능
  - 채널 영상 수가 많을수록 스크롤/수집 시간이 늘어납니다. 라운드마다 전체 재수집하므로 대형 채널은 시간이 길어질 수 있습니다.

## 업데이트 로그
- 2025-10-24
  - YouTube: 채널 검색→동영상 탭 이동→조회수 수집→최저 조회수 영상 재생 로직 추가
  - 조회수 파서 강화(억/만/천, K/M/B, 영어/한국어 혼용), 카드당 스크롤 가시화로 지연 로딩 대응
  - 상세 콘솔 로그 추가(각 단계, 카드별 추출 결과)
  - CSV 저장 시 `saved_at` 컬럼 추가, 재생 대기 시간 옵션 도입
  - 1→N 순차 재생 및 라운드 반복(무한 루프) 구현, 재생 시간은 영상 길이 기반
  - 고정된 16개 제한 제거 → 라운드 시작마다 전체 재수집으로 동적 확장
  - 플랫폼 분리: `youtube_auto_crawl.py`, `kakao_auto_crawl.py`, `naver_auto_crawl.py`로 분리
  - 플랫폼별 CSV 파일명 분리 (`youtube_channel_videos.csv`, `kakaotv_videos.csv`, `navertv_videos.csv`)

## 라이선스
- 본 저장소의 소스코드는 프로젝트 목적 내에서 자유롭게 활용할 수 있습니다. (별도 라이선스 명시 전까지)

## 문의
- 작성자: PotatoDevel0per
- 이슈/개선 제안은 PR 또는 이슈로 남겨주세요.
