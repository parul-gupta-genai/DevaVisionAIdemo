from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from typing import Optional
from loguru import logger
from voice.tts.edge_tts_service import synthesize_speech

router = APIRouter(prefix="/api/tts", tags=["Voice TTS"])

class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Text to synthesize")
    voice: Optional[str] = Field(None, description="Optional specific voice name")
    language: Optional[str] = Field("hi-IN", description="Language code e.g. hi-IN, en-US")
    gender: Optional[str] = Field("male", description="Preferred gender: male or female")
    speed: Optional[float] = Field(1.0, ge=0.25, le=3.0, description="Speech rate multiplier")
    pitch: Optional[float] = Field(1.0, ge=0.25, le=3.0, description="Pitch multiplier")

@router.post("/synthesize")
async def synthesize_text(request: TTSRequest):
    """
    Synthesize text into high-quality neural speech audio (MP3).
    """
    try:
        audio_bytes = await synthesize_speech(
            text=request.text,
            voice=request.voice,
            language=request.language or "hi-IN",
            gender=request.gender or "male",
            speed=request.speed or 1.0,
            pitch=request.pitch or 1.0,
        )
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Synthesis produced empty audio")
            
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"[TTS API] Synthesis error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {str(e)}")
