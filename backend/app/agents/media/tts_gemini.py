"""
Gemini 2.5 Flash TTS — 슬라이드 텍스트 → 나레이션 오디오

반환: WAV 파일 경로 목록 (슬라이드당 1개)
"""
import asyncio
import base64
import os
import struct
import wave
from pathlib import Path
from loguru import logger

AUDIO_DIR = Path(__file__).parents[3] / "output" / "video" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Gemini TTS 한국어 음성 목록
# Kore: 안정적, 명확 / Charon: 낮고 차분 / Aoede: 밝고 활기
KO_VOICES = ["Kore", "Charon", "Aoede"]


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """raw PCM(16-bit mono) → WAV 바이트"""
    buf = bytearray()
    num_samples = len(pcm_bytes) // 2
    byte_rate = sample_rate * 2
    block_align = 2
    data_size = len(pcm_bytes)

    # RIFF 헤더
    buf += b"RIFF"
    buf += struct.pack("<I", 36 + data_size)
    buf += b"WAVE"
    # fmt 청크
    buf += b"fmt "
    buf += struct.pack("<I", 16)        # chunk size
    buf += struct.pack("<H", 1)         # PCM
    buf += struct.pack("<H", 1)         # mono
    buf += struct.pack("<I", sample_rate)
    buf += struct.pack("<I", byte_rate)
    buf += struct.pack("<H", block_align)
    buf += struct.pack("<H", 16)        # bits per sample
    # data 청크
    buf += b"data"
    buf += struct.pack("<I", data_size)
    buf += pcm_bytes

    return bytes(buf)


async def generate_tts_gemini(
    text: str,
    output_path: Path,
    voice_name: str = "Kore",
) -> Path | None:
    """Gemini 2.5 Flash TTS로 단일 텍스트 → WAV 파일 생성"""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("[TTS-Gemini] GEMINI_API_KEY 없음")
        return None

    try:
        import asyncio
        client = genai.Client(api_key=api_key)
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash-preview-tts",
            contents=types.Content(
                role="user",
                parts=[types.Part(text=text)],
            ),
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                ),
            ),
        )

        part = response.candidates[0].content.parts[0]
        # inline_data.data는 이미 bytes — base64 디코딩 불필요
        raw_bytes = part.inline_data.data
        if isinstance(raw_bytes, str):
            raw_bytes = base64.b64decode(raw_bytes)
        mime = part.inline_data.mime_type or ""

        wav_path = output_path.with_suffix(".wav")

        # Gemini는 audio/L16;rate=24000 (raw PCM) 또는 audio/wav 반환
        if "wav" in mime.lower():
            wav_path.write_bytes(raw_bytes)
        else:
            # raw PCM → WAV 래핑
            rate = 24000
            if "rate=" in mime:
                try:
                    rate = int(mime.split("rate=")[1].split(";")[0])
                except Exception:
                    pass
            wav_path.write_bytes(_pcm_to_wav(raw_bytes, sample_rate=rate))

        logger.info(f"  [TTS-Gemini] 저장: {wav_path.name} ({len(raw_bytes)//1024}KB)")
        return wav_path

    except Exception as e:
        logger.error(f"  [TTS-Gemini] 실패: {e}")
        return None


async def generate_narrations_gemini(
    slide_texts: list[str],
    slug: str,
    platform: str,
    voice_name: str = "Kore",
) -> list[Path | None]:
    """슬라이드 목록 → 각각 WAV 파일 생성 (순차 실행 — API rate limit)"""
    logger.info(f"[TTS-Gemini] {len(slide_texts)}개 슬라이드 나레이션 생성 (voice={voice_name})")
    results: list[Path | None] = []

    for i, text in enumerate(slide_texts):
        if not text.strip():
            results.append(None)
            continue

        out_path = AUDIO_DIR / f"{slug}_{platform}_{i:02d}_gemini.wav"

        # 이미 생성된 파일 재사용
        if out_path.exists() and out_path.stat().st_size > 0:
            logger.info(f"  [TTS-Gemini] 슬라이드 {i+1} 재사용")
            results.append(out_path)
            continue

        result = await generate_tts_gemini(text, out_path, voice_name=voice_name)
        results.append(result)

        # API rate limit 방지
        if i < len(slide_texts) - 1:
            await asyncio.sleep(1)

    ok = sum(1 for r in results if r)
    logger.info(f"[TTS-Gemini] 완료: {ok}/{len(slide_texts)}개 성공")
    return results
