import asyncio
import json
import base64
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from voice.interfaces.stt import ISttEngine
from voice.interfaces.tts import ITtsEngine
from voice.interfaces.vad import IVadEngine
from voice.service.chat_integration import VoiceChatIntegration

class VoiceStreamManager:
    """
    Manages the lifecycle of a Voice Chat WebSocket connection.
    Implements streaming, backpressure, and bridging between STT, LLM, and TTS.
    """
    def __init__(self, stt_engine: ISttEngine, tts_engine: ITtsEngine, vad_engine: IVadEngine):
        self.stt = stt_engine
        self.tts = tts_engine
        self.vad = vad_engine
        self.chat_bridge = VoiceChatIntegration()
        
    async def handle_connection(self, websocket: WebSocket):
        await websocket.accept()
        logger.info("Voice WebSocket connected.")
        
        # Audio chunks queue to bridge the websocket receiver and the STT generator
        audio_queue = asyncio.Queue()
        is_receiving = True
        
        async def audio_generator():
            while is_receiving or not audio_queue.empty():
                try:
                    chunk = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
                    if chunk is None:
                        break
                    yield chunk
                except asyncio.TimeoutError:
                    continue
        
        async def process_stt():
            final_text = ""
            async for transcript_event in self.stt.transcribe_stream(audio_generator()):
                if transcript_event["type"] == "partial":
                    await websocket.send_json({
                        "type": "transcript_partial",
                        "text": transcript_event["text"]
                    })
                elif transcript_event["type"] == "final":
                    final_text = transcript_event["text"]
                    await websocket.send_json({
                        "type": "transcript_final",
                        "text": final_text
                    })
                elif transcript_event["type"] == "error":
                    await websocket.send_json({
                        "type": "error",
                        "code": transcript_event.get("code", "STT_ERROR"),
                        "message": transcript_event["message"]
                    })
            return final_text
            
        try:
            # We start an STT task that reads from the queue
            stt_task = None
            
            while True:
                message = await websocket.receive()
                
                if "bytes" in message:
                    audio_chunk = message["bytes"]
                    # If this is the first chunk of a new utterance, start STT
                    if stt_task is None or stt_task.done():
                        # We only start processing if VAD detects speech
                        if self.vad.is_speech(audio_chunk):
                            await websocket.send_json({"type": "status", "state": "listening"})
                            is_receiving = True
                            stt_task = asyncio.create_task(process_stt())
                            await audio_queue.put(audio_chunk)
                    else:
                        await audio_queue.put(audio_chunk)
                        
                elif "text" in message:
                    data = json.loads(message["text"])
                    if data.get("type") == "stop_speaking":
                        # Client stopped speaking, tell generator to finish
                        is_receiving = False
                        await audio_queue.put(None)
                        if stt_task:
                            await websocket.send_json({"type": "status", "state": "processing"})
                            final_transcript = await stt_task
                            stt_task = None
                            
                            if final_transcript:
                                # 1. Send to LLM (run in executor to not block async loop)
                                loop = asyncio.get_running_loop()
                                llm_response = await loop.run_in_executor(None, self.chat_bridge.process_chat_message, final_transcript)
                                
                                await websocket.send_json({
                                    "type": "llm_response",
                                    "text": llm_response
                                })
                                
                                # 2. Optional TTS (if client requested voice response)
                                # For now we assume they want TTS
                                await websocket.send_json({"type": "status", "state": "speaking"})
                                async for tts_chunk in self.tts.synthesize_stream(llm_response):
                                    encoded_audio = base64.b64encode(tts_chunk).decode('utf-8')
                                    await websocket.send_json({
                                        "type": "tts_audio",
                                        "audio_b64": encoded_audio
                                    })
                                    
                            await websocket.send_json({"type": "status", "state": "idle"})
                            
                    elif data.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                        
        except WebSocketDisconnect:
            logger.info("Voice WebSocket disconnected.")
        except Exception as e:
            logger.error(f"Voice Streaming Error: {e}")
            try:
                await websocket.send_json({
                    "type": "error", 
                    "code": "WS_STREAM_ERROR",
                    "message": "A critical streaming error occurred."
                })
            except:
                pass
        finally:
            is_receiving = False
            if stt_task and not stt_task.done():
                stt_task.cancel()
