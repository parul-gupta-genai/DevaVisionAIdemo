from abc import ABC, abstractmethod

class IVadEngine(ABC):
    """
    Interface for Voice Activity Detection.
    Determines if a given audio chunk contains human speech.
    """
    @abstractmethod
    def is_speech(self, audio_chunk: bytes) -> bool:
        pass
