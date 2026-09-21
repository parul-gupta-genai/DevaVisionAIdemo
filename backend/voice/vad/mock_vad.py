from voice.interfaces.vad import IVadEngine

class MockVadEngine(IVadEngine):
    """
    Mock VAD engine that assumes any chunk larger than 100 bytes is speech.
    In a production system, this would use WebRTC VAD or Silero VAD.
    """
    def is_speech(self, audio_chunk: bytes) -> bool:
        # Simple heuristic for the mock: if we have data, it's speech.
        # Silence usually comes in smaller or zero chunks depending on the frontend setup.
        return len(audio_chunk) > 100
