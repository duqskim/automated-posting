"""
YouTube Data API v3 업로드 모듈

기능:
  1. OAuth2 토큰 관리 (파일 저장 + 자동 갱신)
  2. videos.insert() — 영상 업로드
  3. captions.insert() — SRT 자막 업로드
  4. AI 생성 콘텐츠 레이블 (YouTube 2024 정책)

OAuth 초기 설정:
  처음 한 번은 브라우저로 인증이 필요합니다.
  서버가 없는 환경에서는 스크립트로 토큰을 먼저 발급하세요:
    python -m app.agents.publisher.youtube_uploader --init-auth

토큰 저장 위치: backend/app/agents/publisher/youtube_token.json
"""
import json
import os
import time
from pathlib import Path
from loguru import logger

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # captions
]

TOKEN_PATH = Path(__file__).parent / "youtube_token.json"
CATEGORY_EDUCATION = "27"  # YouTube 카테고리: Education


def _load_credentials():
    """저장된 OAuth2 토큰 로드 + 만료 시 자동 갱신"""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET 환경변수 없음")

    if not TOKEN_PATH.exists():
        raise FileNotFoundError(
            f"YouTube 토큰 없음: {TOKEN_PATH}\n"
            "처음 한 번 인증이 필요합니다:\n"
            "  python -m app.agents.publisher.youtube_uploader --init-auth"
        )

    token_data = json.loads(TOKEN_PATH.read_text())
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    if creds.expired and creds.refresh_token:
        logger.info("[YouTube] 토큰 만료 — 갱신 중...")
        creds.refresh(Request())
        TOKEN_PATH.write_text(json.dumps({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
        }))
        logger.info("[YouTube] 토큰 갱신 완료")

    return creds


def _build_youtube_service():
    """YouTube Data API v3 서비스 빌드"""
    from googleapiclient.discovery import build
    creds = _load_credentials()
    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str | Path,
    title: str,
    description: str,
    tags: list[str] | None = None,
    category_id: str = CATEGORY_EDUCATION,
    privacy: str = "private",  # "private" | "unlisted" | "public"
    made_for_kids: bool = False,
    notify_subscribers: bool = False,
) -> dict:
    """
    YouTube에 영상 업로드

    Args:
        video_path: 업로드할 .mp4 파일 경로
        title: 영상 제목 (최대 100자)
        description: 설명 (최대 5000자)
        tags: 태그 목록
        category_id: YouTube 카테고리 ID (기본: Education=27)
        privacy: 공개 설정 ("private" | "unlisted" | "public")
        made_for_kids: 어린이용 콘텐츠 여부
        notify_subscribers: 구독자 알림 여부

    Returns:
        {"video_id": "...", "url": "...", "status": "..."}
    """
    from googleapiclient.http import MediaFileUpload

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일 없음: {video_path}")

    youtube = _build_youtube_service()

    # AI 생성 콘텐츠 레이블 (YouTube 2024 정책)
    if "AI-generated" not in description and "AI generated" not in description:
        description += "\n\n⚠️ This content was created with the assistance of AI tools."

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": (tags or [])[:500],
            "categoryId": category_id,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "madeForKids": made_for_kids,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    if not notify_subscribers:
        body["status"]["publishAt"] = None  # 즉시 업로드, 알림 없음

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB 청크
    )

    logger.info(f"[YouTube] 영상 업로드 시작: {video_path.name} ({video_path.stat().st_size // 1024 // 1024}MB)")

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            logger.info(f"  [YouTube] 업로드 {progress}%")

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info(f"[YouTube] 업로드 완료: {url}")

    return {
        "video_id": video_id,
        "url": url,
        "status": response.get("status", {}).get("uploadStatus", "uploaded"),
    }


def upload_caption(
    video_id: str,
    srt_path: str | Path,
    language: str = "en",
    name: str = "",
) -> dict:
    """
    YouTube 영상에 SRT 자막 업로드

    Args:
        video_id: 대상 YouTube 영상 ID
        srt_path: 업로드할 .srt 파일 경로
        language: 자막 언어 코드 (예: "en", "ko")
        name: 자막 트랙 이름 (예: "English", "Korean")

    Returns:
        {"caption_id": "...", "language": "..."}
    """
    from googleapiclient.http import MediaFileUpload

    srt_path = Path(srt_path)
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT 파일 없음: {srt_path}")

    youtube = _build_youtube_service()

    track_name = name or language.upper()

    body = {
        "snippet": {
            "videoId": video_id,
            "language": language,
            "name": track_name,
            "isDraft": False,
        }
    }

    media = MediaFileUpload(str(srt_path), mimetype="application/octet-stream", resumable=False)

    response = youtube.captions().insert(
        part="snippet",
        body=body,
        media_body=media,
    ).execute()

    caption_id = response.get("id", "")
    logger.info(f"[YouTube] 자막 업로드 완료: {language} ({caption_id})")

    return {"caption_id": caption_id, "language": language}


def init_auth(redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob") -> str:
    """
    초기 OAuth2 인증 흐름 — 브라우저에서 인증 후 코드 입력

    이 함수를 직접 호출하거나:
      python -m app.agents.publisher.youtube_uploader --init-auth

    반환값: 인증 URL (브라우저에서 열어야 함)
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET 환경변수 없음")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(json.dumps({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
    }))
    logger.info(f"[YouTube] 인증 완료 — 토큰 저장: {TOKEN_PATH}")
    return creds.token


def has_valid_token() -> bool:
    """토큰 파일 존재 여부 확인"""
    return TOKEN_PATH.exists()


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[3] / ".env")

    if "--init-auth" in sys.argv:
        print("[YouTube OAuth] 브라우저 인증을 시작합니다...")
        init_auth()
        print(f"[YouTube OAuth] 토큰 저장 완료: {TOKEN_PATH}")
    else:
        print("Usage: python -m app.agents.publisher.youtube_uploader --init-auth")
