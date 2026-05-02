# Automated-Posting 전체 설계 문서

> 작성일: 2026-05-02 | 에이전트 전체 회의 + UX/PM/서비스기획 전문가팀 합의 결과

---

## 1. 시스템 개요

주제 입력 → 리서치 → 콘텐츠 제작 → 이미지/영상 → 발행 자동화
- 사용자: 부부 2인 (기술 능숙자 1 / 일반 사용자 1)
- 언어: 한국어 / 영어 전환 (i18n)
- 주요 출력: YouTube 롱폼 + Shorts

---

## 2. 회의에서 발견된 핵심 문제 (에이전트 자가 진단)

| 에이전트 | 문제 | 심각도 |
|---------|------|--------|
| Research | YouTube API 실제 호출 없음 — 전부 LLM 추정값, 환각 포함 | HIGH |
| Character | reference_image_url이 image_prompter.py에 전달 안 됨 | HIGH |
| Publisher YouTube | 스텁만 있음, 실제 업로드 미구현 | HIGH |
| Shorts | Art Director produce()에 youtube_shorts 누락 — 렌더링 스킵 | MEDIUM |
| SRT | 자막 생성 모듈 자체 없음 | MEDIUM |
| Analytics DB | source_type(ai/upload 구분) 컬럼 없음 | LOW |
| YouTube OAuth | 토큰 저장/갱신 로직 미구현 | MEDIUM |
| Copywriter | Shorts 대본이 롱폼과 독립 병렬 호출 — 롱폼 컨텍스트 미반영 | MEDIUM |

---

## 3. 기술적 제약사항

| 항목 | 내용 | 대응 |
|------|------|------|
| YOUTUBE_API_KEY | .env에 없음 (OAuth만 있음) | GCP Console에서 별도 발급 필요 |
| Imagen 4 reference image | Vertex AI만 지원 (AI Studio 키로 불가) | V2에서 Vertex AI 전환, 지금은 URL을 프롬프트 텍스트에 포함 |
| YouTube API quota | 검색 1회 = 100 units, 10,000 units/day | 에피소드당 1~2회 호출 + 결과 캐싱 |
| SRT 타이밍 | 번역 EN 텍스트 길이 ≠ 한국어 오디오 길이 | TTS 오디오 duration 기준으로 타임스탬프 계산 |
| Shorts 자막 위치 | 9:16 하단 자막이 YouTube UI 버튼과 겹침 | 영상 번인(burn-in) 옵션 제공 |
| SRT 언어 순서 | 한국어 콘텐츠 → KO 자막 기본, EN은 보조 | 콘텐츠 언어 기준으로 기본 자막 결정 |

---

## 4. 개발 로드맵

### Quick Win (지금 당장, ~1시간)
1. **YouTube Data API Key 발급 + Research 연결** (30분)
   - GCP Console → YouTube Data API v3 → API 키 생성
   - `YOUTUBE_API_KEY` .env 추가
   - `ResearcherAgent.analyze_top_content()`에 실제 검색 결과 주입
2. **Director WARN/BLOCK threshold 명시화** (15분)
   - `score < 60` → BLOCK (재생성 강제)
   - `60 <= score < 75` → WARN (사용자 확인 요청)
   - `score >= 75` → PASS
3. **Character reference_image_url 프롬프트 주입** (15분)
   - `image_prompter.py`의 character_note에 URL 포함 (Vertex AI 전환 전 임시 해결)

### MVP (2주)
- Research → YouTube Data API 실제 연결
- X 발행 E2E 완성 (dry_run=False)
- Director WARN/BLOCK 파이프라인 연결
- character reference_image_url 임시 주입

### V1 (3~4주)
- YouTube OAuth + 실제 업로드 구현
- Instagram Meta Graph API 구현
- SRT 자막 생성기 (콘텐츠 언어 기본 + EN 보조)
- YouTube captions.insert() 연동
- AI 라벨 표기 (YouTube 정책 준수)
- Analytics DB source_type 컬럼 추가
- ImagePrompter 협력적 재작성 API + UI

### V2 (이후)
- Vertex AI 전환 → Imagen 4 reference image 완전 지원
- YouTube Shorts 파이프라인 완성
- Dashboard UX 전면 개선 (episode 독립 라우트)
- Analytics 실제 플랫폼 API 연결
- 자기진화 루프 (훅 유형별 이탈률 추적)

---

## 5. 파이프라인 9단계 설계

```
단계   이름                AI 역할              사용자 개입          유형
1      리서치              자동 완전 실행        결과 열람 (선택)     AUTO
2      훅 선택             5개 후보 생성         1개 선택 필수        [KEY]
3      대본 작성           초안 생성             협력 재작성          COLLAB
4      이미지 프롬프트      슬라이드별 생성       전체 승인 필수       [KEY]
5      이미지 생성         자동 생성             직접 업로드 대체 가능 FLEXIBLE
6      영상+TTS            자동 합성             직접 업로드 대체 가능 FLEXIBLE
7      타임라인            자동 조합             순서/길이 조정       EDIT
8      썸네일              자동 생성             직접 업로드 대체 가능 FLEXIBLE
9      발행                스케줄 설정           최종 승인 필수       [KEY]
```

### 확인 모드 3단계
- `KEY_STAGES` (기본): 훅 선택 / 이미지 프롬프트 / 발행 직전 — 3회
- `MANUAL`: 매 단계 확인
- `AUTO`: 발행 직전 1회

### Director WARN/BLOCK
- **BLOCK 조건**: 훅 강도 미달 / 팩트 미확인 통계 / 플랫폼 규격 위반 / AI 라벨 미표기
- **WARN 조건**: 7일 내 유사 주제 / 브랜드 톤 이탈 / 최적 발행시간대 외

---

## 6. YouTube Shorts 설계

### 원칙: 롱폼 파이프라인의 파생(Variant), 별도 프로젝트 아님

### Shorts 대본 구조
- 롱폼 완성 후 순차 생성 (롱폼 body를 컨텍스트로 주입)
- 훅-전개-CTA 구조를 Shorts 전용으로 재설계
- 롱폼의 팩트/데이터는 공유

### 자동 커팅 기준
```
훅 슬라이드 1개 (필수)
+ 데이터/숫자 포함 슬라이드 2~3개 (점수 기준 자동 선택)
+ CTA 슬라이드 1개 (필수)
= 총 4~5 슬라이드, 목표 50~60초 이내
```

### 60초 초과 시
- 클립 재생속도 1.1~1.2x 자동 조정 또는 TTS 단축 버전 재생성 중 선택

### Shorts 기술 사항
- 영상: 9:16, 1080x1920, 30fps, H.264
- 썸네일: 첫 프레임(피드 CTR) + 커스텀 9:16(검색/공유 최적화) 둘 다 생성
- YouTube API: `#Shorts` 해시태그 title/description 필수 포함
- 롱폼과 별도 API 호출 (동시 발행 불가), 쿼터 2배 소모

---

## 7. ImagePrompter 협력적 재작성

### 흐름
```
수정 의도 입력 (한국어 자연어)
    → 프롬프트 미리보기 (before/after 하이라이트)
    → "이대로 생성" 확인
    → 이미지 생성
```

### 효과적인 힌트 유형 (UI에서 제안)
1. 분위기/감정 ("따뜻하고 친근하게") — 여러 파라미터 동시 반영
2. 참조 스타일 ("Apple 광고처럼", "Bloomberg 썸네일처럼")
3. 제거 지시 ("텍스트 없애줘", "사람 빼고") — negative prompt 변환 정확
4. 비효과적: "더 좋게", "예쁘게" — 기준 불명확

### 9:16 vs 16:9 프롬프트 차이
- 9:16: 세로 구도, 피사체 중앙-상단, 하단 1/3 자막 공간 확보
- 16:9: 수평 구도, 좌우 3등분, 와이드 배경 가능

### Image Generator도 동일 적용
- 이미지 재생성 시에도 수정 의도 입력 → AI 프롬프트 재작성 → 생성

---

## 8. 직접 업로드 옵션

### 적용 범위
- 씬 이미지, 영상 클립, TTS 음성, 썸네일, BGM

### UI
- 각 씬 카드에 "직접 업로드" 버튼 + 프롬프트 복사 버튼
- 드래그&드롭 + 파일 선택 모두 지원

### 기술 정규화 (ffmpeg)
- 해상도: 목표 해상도로 강제 스케일
- 프레임레이트: 30fps 통일
- 오디오: `loudnorm` -14 LUFS 정규화
- 가로 영상을 Shorts에 업로드 시: 크롭 / 블러 필 / 박스 선택권 제공

---

## 9. SRT 자막 설계

### 생성 흐름
```
슬라이드별 TTS 오디오 → ffprobe로 duration 측정
    → 누적 타임스탬프 계산
    → SRT 파일 생성
    → (콘텐츠 언어 ≠ EN인 경우) Gemini로 EN 번역
    → YouTube captions.insert() 업로드 (EN + 원본 언어 멀티 트랙)
```

### 언어 우선순위
- 한국어 콘텐츠: KO 자막 기본, EN 보조
- 영어 콘텐츠: EN 자막 기본 (번역 불필요)
- 영어 시장이 우선순위 높음

### 주의사항
- `produce()` 결과에 슬라이드별 audio_duration 리스트 포함 필요 (현재 누락)
- YouTube captions.insert()는 OAuth2 필수 (API 키 방식 불가)

---

## 10. YouTube 발행 설계

### OAuth2 플로우
- `google-auth-oauthlib` 기반 refresh token 파일 저장
- 만료 시 자동 갱신

### 발행 전 체크리스트
```
파일 검증:
  - 영상 파일 존재 및 손상 여부 (ffprobe)
  - Shorts 기준: 9:16 + 60초 이내
  - 최소 해상도 720p 이상

메타데이터:
  - 제목 100자 이하
  - Shorts에 #Shorts 해시태그
  - 썸네일 파일 존재 (2MB 이하)

규정 준수:
  - BGM Content ID 충돌 여부
  - AI 생성 콘텐츠 라벨 (YouTube 2024 정책 의무)
  - 재테크 콘텐츠 면책 문구

중복 방지:
  - DB에 동일 source_id 발행 이력 조회
  - 일일 할당량 잔여량 확인 (10,000 units)
```

### AI 라벨 표기 위치
- YouTube 업로드 시 description에 자동 삽입
- 형식: "이 콘텐츠는 AI를 활용해 제작됐습니다 | Created with AI assistance"

---

## 11. UX 설계

### 레이아웃: Wizard-in-Shell
```
┌───────────┬──────────────────────────────────────────────┐
│  SIDEBAR  │  Step Rail (1→2→3→4→5→6→7→8→9) 상단 고정   │
│           ├──────────────────────────────────────────────┤
│  프로젝트  │                                              │
│  시리즈   │         ACTIVE STEP WORKSPACE               │
│  캐릭터   │                                              │
│  Analytics├──────────────────────────────────────────────┤
│           │  Bottom Action Bar: [이전] [저장] [다음]     │
└───────────┴──────────────────────────────────────────────┘
```

### 사이트맵 (목표)
```
/dashboard                  홈 — 오늘의 파이프라인 + 발행 캘린더
/projects                   프로젝트 목록
/projects/[id]              프로젝트 홈 (개요/콘텐츠/캐릭터/Analytics 탭)
/episodes/[id]              에피소드 워크스페이스 (9단계) ← 핵심
/series                     시리즈 목록
/series/[id]                시리즈 상세
/characters/[id]            캐릭터 스튜디오 (5단계)
/accounts                   SNS 계정 연결
/analytics                  통합 성과 대시보드
/settings                   언어/알림/구독
```

### i18n
- 기술 스택: `next-intl`
- 우상단 `KO / EN` 토글 (URL 기반 아닌 localStorage + Context)
- UI 레이블만 전환 — AI 생성 콘텐츠는 그대로
- 콘텐츠 생성 언어는 에피소드별 별도 설정

### 타임라인 편집기 최소 기능 (Tier 1)
1. 클립 순서 변경 (드래그 또는 인덱스)
2. 클립별 재생 길이 수동 지정 (초 단위)
3. 특정 클립 제외
4. TTS 텍스트 수정 후 해당 클립만 재합성
5. 전체 미리보기 (저해상도 프리뷰)

### 실수 방지 TOP 6
1. KEY_STAGE 미완료 시 다음 단계 버튼 비활성
2. 발행 전 최종 확인 모달 (제목/공개범위/시간 요약)
3. 비율 혼동 방지 (업로드 시 자동 감지 + 경고)
4. 이미지 프롬프트 미승인 카운터 표시
5. 캐릭터 미배정 경고 배너
6. 동일 훅 유형 연속 사용 경고

---

## 12. Analytics 자기진화 루프

### 통합 참여 점수
- Shorts: `시청완료율×0.6 + 좋아요율×0.4`
- 롱폼: `평균시청시간/총길이×0.5 + CTR×0.5`
- 동일 DB 컬럼, 포맷별 가중치만 다르게

### 필수 추적 3가지
1. 훅 문장 유형별 첫 3초 이탈률
2. 해시태그 조합별 Reach 증가율
3. 직접 업로드 vs AI 생성 저장율/CTR 차이

### DB 추가 필요
- `media_assets.source_type`: `enum("ai_generated", "direct_upload")`
- `publish_results.platform_post_id`: 발행 후 YouTube video_id 저장 → Analytics 연결

---

## 13. 캐릭터 시스템

### 위치: 시리즈 생성 시 1회 완성 → 에피소드마다 재사용
- 에피소드 파이프라인에서 "선택사항"으로 추가하면 일관성 붕괴
- `design_session.stage == "done"` 캐릭터만 에피소드 제작에 참여 가능

### reference_image_url 처리
- 현재: DB에 저장되지만 image_prompter.py에 미전달
- Quick Fix: character_note에 URL 텍스트 포함 (즉시)
- Full Fix: Vertex AI 전환 후 이미지 파라미터로 전달 (V2)

### Shorts(9:16) 캐릭터 구도
- 중앙 하단 1/3 배치, 상단 2/3 자막 영역
- 상반신 클로즈업 권장 (전신 금지)
- image_prompter.py에 `platform="youtube_shorts"` 분기 추가 필요

---

## 14. KPI

| KPI | 목표 | 현재 |
|-----|------|------|
| 파이프라인 완주율 | MVP: >70%, V1: >90% | 0% (Publisher 전부 실패) |
| 리서치 팩트 밀도 | MVP 후: >60% | 0% (전부 LLM 추정) |
| 캐릭터 시각 일관성 | V1 후: >50% | 0% (URL 미전달) |

---

## 15. 합의된 Shorts SRT 동작

- 롱폼 SRT와 별도 생성 (타임라인이 다름)
- EN 기본 + KO 옵션 (영어 시장 우선)
- 한국어 콘텐츠인 경우: KO 기본 + EN 보조
- Shorts 화면 번인(burn-in) 옵션 별도 제공 (API 자막 위치 제어 불가 문제)
