import io
import edge_tts
from loguru import logger
from typing import Optional

# Voice mappings for multi-language & gender support
VOICE_MAP = {
    "hi-IN": {
        "male": "hi-IN-MadhurNeural",
        "female": "hi-IN-SwaraNeural",
    },
    "en-IN": {
        "male": "en-IN-PrabhatNeural",
        "female": "en-IN-NeerjaNeural",
    },
    "en-US": {
        "male": "en-US-GuyNeural",
        "female": "en-US-JennyNeural",
    },
    "en-GB": {
        "male": "en-GB-RyanNeural",
        "female": "en-GB-SoniaNeural",
    },
    "es-ES": {
        "male": "es-ES-AlvaroNeural",
        "female": "es-ES-ElviraNeural",
    },
    "fr-FR": {
        "male": "fr-FR-HenriNeural",
        "female": "fr-FR-DeniseNeural",
    },
    "de-DE": {
        "male": "de-DE-ConradNeural",
        "female": "de-DE-KatjaNeural",
    },
    "ar-SA": {
        "male": "ar-SA-HamedNeural",
        "female": "ar-SA-ZariyahNeural",
    },
}

def resolve_voice_name(language: str = "hi-IN", gender: str = "male", requested_voice: Optional[str] = None) -> str:
    """Resolves the best Microsoft Neural voice name based on language and gender."""
    if requested_voice and "Neural" in requested_voice:
        return requested_voice
    
    lang_key = language if language in VOICE_MAP else "hi-IN"
    gender_key = "female" if gender.lower() == "female" else "male"
    
    return VOICE_MAP.get(lang_key, {}).get(gender_key, "hi-IN-MadhurNeural")

async def synthesize_speech(
    text: str,
    voice: Optional[str] = None,
    language: str = "hi-IN",
    gender: str = "male",
    speed: float = 1.0,
    pitch: float = 1.0,
) -> bytes:
    """
    Synthesizes speech using Microsoft Neural TTS and returns MP3 audio bytes.
    """
    clean_text = text.strip()
    if not clean_text:
        return b""
    
    target_voice = resolve_voice_name(language=language, gender=gender, requested_voice=voice)
    
    # Calculate SSML rate and pitch deltas
    speed_percent = int(round((speed - 1.0) * 100))
    rate_str = f"{speed_percent:+d}%" if speed_percent != 0 else "+0%"
    
    pitch_hz = int(round((pitch - 1.0) * 50))
    pitch_str = f"{pitch_hz:+d}Hz" if pitch_hz != 0 else "+0Hz"
    
    logger.debug(f"[EdgeTTS] Synthesizing with voice={target_voice}, rate={rate_str}, pitch={pitch_str}")
    
    communicate = edge_tts.Communicate(clean_text, target_voice, rate=rate_str, pitch=pitch_str)
    buffer = io.BytesIO()
    
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
            
    return buffer.getvalue()
