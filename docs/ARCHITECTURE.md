# automated-posting 시스템 아키텍처

## 개요

주제 입력 → 리서치 → 콘텐츠 작성 → 이미지/영상 제작 → 자동 발행
멀티마켓(한국/북미/일본), 멀티유저, 10개 에이전트 파이프라인

---

## 시장 선택형 아키텍처

프로젝트 생성 시 시장(KR/US/JP) 선택 → 전체 파이프라인 로직이 바뀜

### 시장별 차이

| | 🇰🇷 한국 | 🇺🇸 북미 | 🇯🇵 일본 |
|---|---------|---------|---------|
| 언어 | 한국어 | 영어 | 일본어 |
| 톤 | 친근한 존댓말 (~해요) | 캐주얼 1인칭 | 丁寧語 (ですます) |
| 훅 스타일 | 집단형 ("직장인 87%가...") | 개인형 ("I spent 6 months...") | 발견형 ("知らないと損...") |
| 정보 밀도 | 높음 (40~60자/슬라이드) | 낮음 (8~12단어/슬라이드) | 중간 |
| 주요 플랫폼 | IG, YT, Threads, 네이버 | YT, LinkedIn, Newsletter, IG | YT, IG, X, note.com |
| 검색 SEO | 네이버 | Google | Google JP |
| 공유 최적화 | 카카오톡 | 이메일/DM | LINE |
| 해시태그 | 5개 한국어 | 3개 영어 | 5개 일본어 |
| 트렌드 주기 | 48시간 | 120시간 | 72시간 |
| 썸네일 스타일 | 텍스트 중심 | 얼굴+짧은 텍스트 | 텍스트+일러스트 |

### 리서치 소스

| 🇰🇷 한국 | 🇺🇸 북미 | 🇯🇵 일본 |
|----------|----------|----------|
| 네이버 DataLab | Google Trends US | Google Trends JP |
| 한국경제/매경/테크42 RSS | TechCrunch/Verge RSS | Yahoo Japan |
| YouTube 검색 (KR) | Reddit trending | note.com RSS |
| Instagram 해시태그 (KR) | Hacker News | X Trends JP |
| | YouTube 검색 (EN) | YouTube 검색 (JP) |

---

## 에이전트 파이프라인 (10개)

```
┌──────────────────────────────────────────────────────────────┐
│                Pipeline Controller (코드)                     │
│   market_profile 로드 → 모든 에이전트에 주입                    │
│   긴급 모드(자동) / 일반 모드(리뷰) 분기                        │
│   민감 이벤트 서킷 브레이커                                     │
└──────────┬───────────────────────────────────────────────────┘
           │
    ┌──────▼──────────┐
    │ 0. Watchdog      │  코드 (백그라운드 상시)
    │   경쟁자 감시     │  경쟁 계정 모니터링 → 터진 주제 감지
    │                  │  민감 이벤트 감지 → 발행 중단
    └──────┬──────────┘
           │
    ┌──────▼──────────┐
    │ 1. Researcher    │  Gemini Flash
    │                  │  주제 → 키워드 확장 → 플랫폼별 상위 콘텐츠 분석
    │                  │  → winning formula + 경쟁자 빈틈 발견
    └──────┬──────────┘
           │
    ┌──────▼──────────┐
    │ 2. Hooksmith     │  Claude Sonnet
    │                  │  winning formula 기반 훅 3~5개 + 썸네일 카피 3개
    │                  │  → 품질 게이트: 10단어 이내? 호기심 갭? 숫자?
    └──────┬──────────┘
           │
    ┌──────▼──────────┐
    │ 3. Copywriter    │  Claude Sonnet (플랫폼별 독립 호출)
    │                  │  시리즈 컨텍스트 주입 (이전 회차 참조)
    │                  │  플랫폼별 "재해석" (리포맷 ✕)
    └──────┬──────────┘
           │
    ┌──────▼──────────┐
    │ 4. Quality Gate  │  코드 (LLM 호출 없음)
    │   자동 검수       │  ① AI 티 검출 + 자동 수정
    │                  │  ② 훅 강도 점수
    │                  │  ③ 정보 밀도 체크
    │                  │  ④ 팩트 체크 (출처 없는 통계 제거)
    │                  │  ⑤ 플랫폼 규격 준수 (글자수, 해시태그)
    │                  │  ⑥ 카카오톡/이메일 공유 시 가독성
    │                  │  ⑦ 민감 키워드 필터
    │                  │  → 기준 미달 시 Copywriter에 재작업 (1회)
    └──────┬──────────┘
           │
    ┌──────▼──────────┐
    │ 5. Art Director  │  Playwright + 코드
    │                  │  이미지 + 썸네일 (A/B 변형 2~3개)
    │                  │  네이버 블로그/뉴스레터용 OG 이미지
    └──────┬──────────┘
           │
    ┌──────▼──────────┐
    │ 6. Producer      │  moviepy + ElevenLabs
    │                  │  나레이션 → 클립 → 롱폼/숏폼 조립
    │                  │  자막 + BGM + 트랜지션
    └──────┬──────────┘
           │
    ┌──────▼──────────┐   일반 모드: 사용자 리뷰
    │ 7. 사용자 리뷰    │   긴급 모드: 스킵
    └──────┬──────────┘
           │
    ┌──────▼──────────┐
    │ 8. Publisher      │  플랫폼별 API
    │                  │  KR: IG, YT, Threads, 네이버, 카카오톡
    │                  │  US: YT, LinkedIn, Newsletter, IG, Reddit, Pinterest
    │                  │  JP: YT, IG, X, note.com
    │                  │  + 타임존 변환 + 예약 발행
    │                  │  + A/B 썸네일 테스트
    └──────┬──────────┘
           │
    ┌──────▼──────────┐
    │ 9. Engager       │  코드 + LLM (알림용)
    │   댓글 매니저     │  댓글 모니터링 → 알림 → 답변 초안 추천
    │                  │  자동 답변은 안 함 (리스크)
    └──────┬──────────┘
           │
    ┌──────▼──────────┐
    │ 10. Analyst      │  Gemini Flash (백그라운드)
    │                  │  성과 수집 → A/B 결과 분석
    │                  │  → winning content few-shot 피드백
    │                  │  → 시리즈 성과 트래킹
    └──────────────────┘
```

---

## 기술 스택

| 레이어 | 기술 | 이유 |
|--------|------|------|
| 프론트엔드 | Next.js 14 + Tailwind + shadcn/ui | 직관적 UI, 로그인 |
| 백엔드 | FastAPI (Python 3.12) | LLM 생태계, 비동기 |
| 인증 | JWT (email/password) | 심플, 2인 사용 |
| DB | PostgreSQL 16 | 멀티유저, JSONB |
| ORM | SQLAlchemy 2.0 + Alembic | 마이그레이션 |
| 작업큐 | Celery + Redis | 장시간 작업 (영상 렌더링 등) |
| LLM (리서치) | Gemini 2.5 Flash | 빠르고 저렴 |
| LLM (글쓰기) | Claude Sonnet 4 | 한국어/영어 글쓰기 품질 최고 |
| 음성 | ElevenLabs API | 최고 품질 TTS, 다국어 |
| 이미지 | Jinja2 + Playwright | 한국어/일본어 텍스트 완벽 렌더링 |
| 영상 | moviepy + ffmpeg | 무료, 프로그래밍적 제어 |
| 이미지 호스팅 | Cloudinary | 무료 25GB |
| 컨테이너 | Docker Compose | PostgreSQL + Redis |

---

## 데이터베이스 핵심 테이블

```
users                 -- 사용자 (로그인)
sns_accounts          -- 사용자별 SNS 계정 (시장별 분리)
projects              -- 주제별 프로젝트 (시장 포함)
brand_profiles        -- 시장별 브랜드 프로필
content_series        -- 시리즈 관리
research_results      -- 리서치 결과
content_plans         -- 콘텐츠 플랜
media_assets          -- 이미지, 영상, 음성, 썸네일
publish_results       -- 발행 결과
post_metrics          -- 성과 지표
jobs                  -- Celery 작업 추적
content_templates     -- HTML/CSS 이미지 템플릿
competitor_accounts   -- 경쟁자 모니터링
ab_test_variants      -- A/B 테스트
comment_alerts        -- 댓글 알림
sensitive_events      -- 민감 이벤트 로그
```

---

## LLM 비용 (콘텐츠 1개당)

| 호출 | 모델 | 비용 |
|------|------|------|
| Researcher (1~2회) | Gemini Flash | ~$0.005 |
| Hooksmith (1회) | Claude Sonnet | ~$0.01 |
| Copywriter (3~5회, 플랫폼별) | Claude Sonnet | ~$0.05 |
| Quality Gate | 코드 (무료) | $0 |
| Analyst (주간) | Gemini Flash | ~$0.005 |
| **총 토픽 1개** | | **~$0.07~0.10** |
| ElevenLabs 숏폼 음성 | | ~$0.03 |
| ElevenLabs 롱폼 음성 | | ~$0.15 |
| **총 (음성 포함)** | | **~$0.15~0.30** |

---

## 벤치마킹 서비스

| 서비스 | 참고 포인트 |
|--------|------------|
| Predis.ai | 텍스트→이미지→발행 원스톱 파이프라인 |
| Lately.ai | 성과 기반 자기 진화 AI (few-shot 피드백 루프) |
| ContentStudio | 콘텐츠 발견 + 멀티채널 발행 |
| Opus Clip | 롱폼→숏폼 변환 + 바이럴 스코어 |
| Jasper AI | 브랜드 보이스 학습 + 마케팅 카피 |
| Canva | 비주얼 템플릿 + 브랜드 키트 |
| Buffer / Later | 멀티플랫폼 예약 발행 UX |

**핵심 차별점:** 한국어 네이티브 엔드투엔드 + 멀티마켓 자동화 서비스는 시장에 없음

---

## 구현 순서

### Phase 1 (1~2주): 기반 ✅
- 모노레포 (backend + frontend)
- Docker Compose + DB 마이그레이션
- 인증 (JWT)
- Market Profile 시스템 (KR/US/JP)
- SNS 계정 관리 API
- LLM 추상 레이어 (Claude + Gemini)
- 개발/검수 에이전트 (Linter, Tester, Reviewer, Ship Agent)

### Phase 2 (3~4주): 리서치 + 글쓰기 ✅
- Researcher Agent (주제 기반 동적 리서치, 키워드 확장, 상위 콘텐츠 분석)
- Hooksmith Agent (훅 3~5개 생성, 썸네일 카피)
- Copywriter Agent (플랫폼별 독립 콘텐츠 생성, 10개 플랫폼 포맷 지원)
- Quality Gate (AI 티 검출, 훅 강도 점수, 팩트 체크, 민감 키워드 필터)
- Pipeline Controller (에이전트 오케스트레이션, 실패 시 1회 재생성)
- Pipeline API (리서치/전체 실행/미리보기)
- Celery 연동: 미구현 (다음)
- UI: 미구현 (다음)

### Phase 3 (5~6주): 미디어 + 발행 + 분석 ✅
- Art Director (이미지/썸네일)
- Producer (나레이션/영상)
- 템플릿 시스템 + 브랜드 커스터마이징
- UI: 미리보기/편집

### Phase 4 (7~8주): 발행 + 완성
- Publisher (플랫폼별)
- 예약 발행 + 타임존 변환
- Engager (댓글 알림)
- Analyst (성과 피드백)
- Watchdog (경쟁자 감시)
- UI: 발행 컨트롤 + 분석 대시보드

### Phase 5 (9주+): 확장
- 일본 시장 Market Profile
- A/B 테스트 자동화
- 시리즈 콘텐츠 관리
- 네이버 블로그 / 뉴스레터 연동

---

## 개발/검수 에이전트 (Dev Agents)

서비스 에이전트와 별도로, 개발 품질 관리를 위한 에이전트 체계:

```
┌──────────────────────────────────────────┐
│            Ship Agent (총괄)              │
│   자체검증→테스트→리뷰→md업데이트→커밋     │
└─────────┬──────────┬──────────┬──────────┘
          │          │          │
   ┌──────▼───┐ ┌───▼────┐ ┌──▼───────┐
   │ Linter   │ │ Tester │ │ Reviewer │
   │ Agent    │ │ Agent  │ │ Agent    │
   └──────────┘ └────────┘ └──────────┘
```

| 에이전트 | 역할 |
|---------|------|
| **Linter Agent** | ruff 린트, mypy 타입 체크, 보안 취약점 탐지 |
| **Tester Agent** | pytest 실행, import 체크, 커버리지 |
| **Reviewer Agent** | 함수 길이 검사, TODO/FIXME 수집, 미사용 import 탐지 |
| **Ship Agent** | 위 3개 순서대로 실행 → 전부 통과 시 md 업데이트 + 커밋 + push |

### 개발 워크플로우 (필수)

모든 개발/수정/보완 완료 시 반드시:
```
1. 자체검증 (Linter Agent)
2. 테스트   (Tester Agent)
3. 코드 리뷰 (Reviewer Agent)
4. 문서 업데이트 (ARCHITECTURE.md 등)
5. 커밋 + Push
```

---

## 운영 참고

- 한국에서 북미 계정 운영 가능 (TikTok 제외)
- 북미 최적 발행 시간 = KST 새벽 → 예약 발행 필수
- 시장별 계정 반드시 분리 (언어 혼용 시 알고리즘 페널티)
