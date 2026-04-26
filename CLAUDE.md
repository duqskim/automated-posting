# automated-posting

SNS 자동 콘텐츠 제작/발행 시스템 — 멀티마켓(KR/US/JP)

---

## 커스텀 명령어

### /doit
개발 완료 후 실행하는 표준 마무리 루틴:

1. **검증** — 변경된 파일 확인, import 오류 및 명백한 버그 점검
2. **보완** — 발견된 문제 수정 (import 위치, 타입 오류, 누락된 처리 등)
3. **리팩토링** — 중복 코드 제거, 불필요한 import 정리, 가독성 개선 (최소한으로)
4. **CLAUDE.md 업데이트** — 진행 현황 테이블 갱신 (완료/진행중/예정)
5. **커밋** — `git add` + `git commit` (컨벤션: `feat:` / `fix:` / `refactor:`)

---

## 프로젝트 구조

```
automated-posting/
├── backend/                  # FastAPI (Python 3.12)
│   ├── app/
│   │   ├── main.py           # FastAPI 앱 + 라우터 등록 + 정적 파일 마운트
│   │   ├── auth/             # JWT 인증
│   │   ├── models/           # SQLAlchemy 모델 (SQLite)
│   │   ├── api/              # REST API 라우터
│   │   │   ├── pipeline.py   # 콘텐츠 제작 파이프라인
│   │   │   ├── series.py     # 시리즈/에피소드
│   │   │   └── character.py  # 캐릭터 디자인 스튜디오
│   │   ├── agents/           # LLM 에이전트
│   │   │   ├── pipeline.py   # 파이프라인 컨트롤러
│   │   │   ├── writer/       # 글쓰기 에이전트
│   │   │   ├── media/        # 이미지/영상 제작
│   │   │   └── character/    # 캐릭터 디자인 5단계
│   │   └── llm/              # LLM 클라이언트 (Claude, Gemini)
│   └── output/               # 생성된 파일
│       ├── characters/       # 캐릭터 이미지 → /api/characters/
│       ├── scenes/           # 씬 이미지 → /api/scenes/
│       └── video/            # 영상 → /api/videos/
│
└── frontend/                 # Next.js 14 + Tailwind + shadcn/ui
    └── src/app/
        ├── series/[id]/      # 시리즈 상세
        └── series/[id]/character/[charId]/  # 캐릭터 디자인 스튜디오
```

---

## LLM 역할 분담

| 역할 | 모델 | 용도 |
|------|------|------|
| `character_design` | Claude Opus 4.6 | 아키타입/컨셉/바이블 — IP 창작 |
| `research` | Gemini 2.5 Pro | 리서치/분석 |
| `writing` / `hooksmith` | Claude Sonnet 4.6 | 콘텐츠 글쓰기 |
| `analysis` | Gemini 2.5 Flash | 데이터 분석, 기타 |
| 이미지 생성 | Gemini 3 Pro Image | 캐릭터 이미지 (Imagen 4.0 fallback) |

---

## 캐릭터 디자인 파이프라인

```
Stage 1: 오디언스 리서치 (Gemini 2.5 Pro)
Stage 2: 아키타입 추천 3개 (Claude Opus 4.6)
Stage 3: 컨셉 생성 3개 (Claude Opus 4.6)
Stage 4: 비주얼 이미지 생성 (Gemini 3 Pro Image)
Stage 5: Character Bible 작성 (Claude Opus 4.6, max_tokens=8192)
```

완성된 캐릭터 (status=active)는 파이프라인 write/render 단계에 자동 주입됨.

---

## 진행 현황

### 완료

| 기능 | 비고 |
|------|------|
| JWT 인증 (회원가입/로그인) | |
| 프로젝트/시리즈/에피소드 CRUD | |
| 6단계 콘텐츠 파이프라인 | 리서치→훅→글쓰기→이미지→영상 |
| 캐릭터 디자인 스튜디오 5단계 | |
| 캐릭터 → 파이프라인 자동 연동 | 글쓰기/이미지에 캐릭터 목소리/비주얼 주입 |
| 이미지 생성 Gemini 3 Pro Image | Imagen 4.0 fallback |
| 캐릭터 생성 진행 상태 표시 | 단계별 진행바 + 모델명 |

### 예정

| 기능 | 우선순위 |
|------|---------|
| 계정별 파일 분리 (user_id/project_id) | 중 |
| SQLite WAL 모드 (2인 동시 사용) | 중 |
| 배포 환경 (Docker + PostgreSQL) | 낮 |
| 로그 시스템 (loguru 파일) | 낮 |
| UX 전체 플로우 점검 | 낮 |

---

## 실행

```bash
# 백엔드 (backend/ 디렉토리에서)
uvicorn app.main:app --reload --port 8000

# 프론트엔드 (frontend/ 디렉토리에서)
npm run dev
```
