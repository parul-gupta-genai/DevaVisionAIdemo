from fastapi import APIRouter, WebSocket, Depends
from voice.streaming.manager import VoiceStreamManager
from voice.stt.mock_stt import LiveSttEngine
from voice.tts.mock_tts import MockTtsEngine
from voice.vad.mock_vad import MockVadEngine

voice_router = APIRouter()

# In a real enterprise app, we would inject these via dependency injection
# For now we use the mock implementations
def get_voice_manager() -> VoiceStreamManager:
    return VoiceStreamManager(
        stt_engine=LiveSttEngine(),
        tts_engine=MockTtsEngine(),
        vad_engine=MockVadEngine()
    )

@voice_router.websocket("/ws/voice/chat")
async def voice_chat_endpoint(websocket: WebSocket, manager: VoiceStreamManager = Depends(get_voice_manager)):
    """
    WebSocket endpoint for bidirectional voice streaming.
    Requires authentication via token (omitted here for brevity, handled by middleware or token param in prod).
    """
    await manager.handle_connection(websocket)
