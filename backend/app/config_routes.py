from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict
from pydantic import BaseModel

from config.config import config, sanitize_counting_line, MIN_COUNTING_LINE_LEN
from app.auth.dependencies import require_permissions, get_current_user

config_router = APIRouter(tags=["configuration"])

class ConfigUpdate(BaseModel):
    # A generic dict to update top-level config keys
    updates: Dict[str, Any]

_MAX_COUNTING_LINES = 8

def _normalized_counting_lines(value: Any) -> dict:
    """
    Validates and normalizes a COUNTING_LINES update so garbage can never
    reach the live pipeline: {camera_id: null | [{id, name, start, end}, ...]}.
    A null entry deletes the per-camera override (reset to the default line).
    Per-line normalization is shared with the counting plugin via
    config.sanitize_counting_line so API and pipeline can never drift.
    """
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="COUNTING_LINES must map camera ids to line lists")

    normalized: dict = {}
    for cam_id, lines in value.items():
        if lines is None:
            if cam_id == "default":
                # Deleting the built-in default would turn crossing counting
                # off for every camera without a custom override.
                raise HTTPException(
                    status_code=422,
                    detail="COUNTING_LINES['default'] cannot be deleted — set an explicit list instead",
                )
            normalized[cam_id] = None
            continue
        if not isinstance(lines, list) or len(lines) > _MAX_COUNTING_LINES:
            raise HTTPException(
                status_code=422,
                detail=f"COUNTING_LINES['{cam_id}'] must be a list of at most {_MAX_COUNTING_LINES} lines",
            )
        clean_lines = []
        for idx, line in enumerate(lines):
            norm = sanitize_counting_line(line, idx)
            if norm is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"COUNTING_LINES['{cam_id}'][{idx}] is not a valid counting line "
                        f"(needs numeric start/end [x, y] pairs at least {MIN_COUNTING_LINE_LEN}px apart)"
                    ),
                )
            clean_lines.append(norm)
        normalized[cam_id] = clean_lines
    return normalized

_MAX_SAMPLING_INTERVAL = 300

# Plugins whose logic depends on consecutive frames (line crossings, centroid
# tracking, tripwires). Sampling these drops the intermediate positions their
# crossing tests are built on, so counts silently degrade.
_UNSAMPLEABLE_PLUGINS = {
    "PeopleCountingPlugin",
    "CartonCountingPlugin",
    "VisitorPlugin",
    # Re-derives identity per run and evaluates a turnstile crossing from
    # consecutive centroids; sampling makes it mint new ids and miss or
    # fabricate CHECK IN / CHECK OUT events.
    "AttendanceDetectionPlugin",
    # Every signal it uses — speed, direction reversal, separation — is a
    # difference between two consecutive observations of the same person.
    # Sampled, the intermediate positions vanish and a struggle reads as a
    # sequence of unrelated jumps.
    "FightDetectionPlugin",
}


def _normalized_plugin_sampling(value: Any) -> dict:
    """
    Validates a PLUGIN_SAMPLING update: {plugin_name: int >= 1 | null}.
    A null resets the plugin to every-frame. Rejects intervals on plugins
    that need consecutive frames rather than silently breaking their counts.
    """
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=422,
            detail="PLUGIN_SAMPLING must map plugin names to frame intervals",
        )

    normalized: dict = {}
    for plugin_name, interval in value.items():
        if interval is None:
            normalized[plugin_name] = None
            continue
        if isinstance(interval, bool) or not isinstance(interval, int):
            raise HTTPException(
                status_code=422,
                detail=f"PLUGIN_SAMPLING['{plugin_name}'] must be an integer",
            )
        if not 1 <= interval <= _MAX_SAMPLING_INTERVAL:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"PLUGIN_SAMPLING['{plugin_name}'] must be between 1 and "
                    f"{_MAX_SAMPLING_INTERVAL} frames"
                ),
            )
        if interval > 1 and plugin_name in _UNSAMPLEABLE_PLUGINS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{plugin_name} tracks movement across consecutive frames "
                    f"and must run at interval 1"
                ),
            )
        normalized[plugin_name] = interval
    return normalized


def _persist_to_dotenv(updates: dict):
    try:
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_file = os.path.join(base_dir, ".env")
        lines = []
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        
        env_dict = {}
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_dict[k.strip()] = v.strip()
        
        for k, v in updates.items():
            if v is not None and v != "***":
                env_dict[k] = str(v)
                
        with open(env_file, "w", encoding="utf-8") as f:
            for k, v in env_dict.items():
                f.write(f"{k}={v}\n")
    except Exception:
        pass

@config_router.get("/api/config", dependencies=[Depends(get_current_user)])
async def get_config() -> Any:
    """Get the current running configuration (excluding secrets)."""
    # Create a safe copy of config without secrets
    safe_config = config.model_dump()
    if "SECRET_KEY" in safe_config:
        del safe_config["SECRET_KEY"]
    if "OPENAI_API_KEY" in safe_config and safe_config["OPENAI_API_KEY"]:
        safe_config["OPENAI_API_KEY"] = "***"
        
    return safe_config

@config_router.post("/api/config", dependencies=[Depends(get_current_user)])
async def update_config(
    update_data: ConfigUpdate
) -> Any:
    """Update running configuration in memory (and persist per-camera state)."""
    MUTABLE_KEYS = {
        "CAMERA_PLUGINS", "RESTRICTED_ZONES", "PARKING_SPOTS", "CHECKIN_LINES",
        "COUNTING_LINES", "PLUGIN_SAMPLING", "CAMERA_FPS",
        "CONFIDENCE_THRESHOLD", "FRAME_SKIP", "GESTURE_ENABLED", "TRACKER_BACKEND",
        "LOITERING_THRESHOLD_SECONDS", "LLM_PROVIDER", "GROQ_API_KEY", "GROQ_MODEL",
        "OLLAMA_BASE_URL", "OLLAMA_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL",
        "VOICE_STT_ENGINE", "VOICE_TTS_ENGINE", "VOICE_LANGUAGE", "VOICE_GENDER",
        "VOICE_SPEED", "VOICE_PITCH", "VOICE_VOLUME", "VOICE_NAME",
        "VOICE_RIVA_SERVER", "VOICE_KOKORO_VOICE", "VOICE_RIVA_VOICE",
    }
    import redis, json

    def _publish_live_update(payload: dict):
        """Forwards the change to the DeepStream process (its plugin engine
        reads the same config module, but in a separate process)."""
        try:
            r = redis.Redis.from_url(config.REDIS_URL)
            r.publish("config:plugins_updated", json.dumps(payload))
        except Exception:
            pass

    llm_keys_updated = False
    env_updates = {}
    try:
        for key, value in update_data.updates.items():
            if key not in MUTABLE_KEYS:
                # Ignore non-mutable keys (e.g. read-only config keys returned from GET /api/config)
                continue

            if key in {
                "LLM_PROVIDER", "GROQ_API_KEY", "GROQ_MODEL", "OLLAMA_BASE_URL", "OLLAMA_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL",
                "VOICE_STT_ENGINE", "VOICE_TTS_ENGINE", "VOICE_LANGUAGE", "VOICE_GENDER", "VOICE_SPEED", "VOICE_PITCH", "VOICE_VOLUME", "VOICE_NAME",
                "VOICE_RIVA_SERVER", "VOICE_KOKORO_VOICE", "VOICE_RIVA_VOICE"
            }:
                llm_keys_updated = True
                env_updates[key] = value

            if key == "COUNTING_LINES":
                value = _normalized_counting_lines(value)
            elif key == "PLUGIN_SAMPLING":
                value = _normalized_plugin_sampling(value)

            if hasattr(config, key):
                current_val = getattr(config, key)
                if isinstance(current_val, dict) and isinstance(value, dict):
                    # Safely merge dictionary updates (like CAMERA_PLUGINS) by creating a new copy
                    # This ensures Pydantic V2 detects the change and updates model_dump().
                    # A null value deletes the per-camera override (reset to default).
                    new_val = current_val.copy()
                    for sub_key, sub_val in value.items():
                        if sub_val is None:
                            new_val.pop(sub_key, None)
                        else:
                            new_val[sub_key] = sub_val
                    setattr(config, key, new_val)

                    if key in config.PERSISTED_DICT_KEYS:
                        config.save_plugins_state()
                        _publish_live_update({key: value})
                    else:
                        _publish_live_update({key: new_val})

                    if key == "CAMERA_PLUGINS":
                        from core.state import sync_camera_plugins
                        from core.camera_manager import camera_manager
                        for cam_id, p_list in value.items():
                            sync_camera_plugins(cam_id, p_list)
                            camera_manager.evaluate_auto_suspend(cam_id)
                else:
                    setattr(config, key, value)
                    _publish_live_update({key: value})

        # Persist LLM settings to .env file and reset agent
        if llm_keys_updated:
            _persist_to_dotenv(env_updates)
            try:
                from agents.chat_agent import agent
                agent._agent = None
            except Exception:
                pass

        return {"status": "success", "message": "Configuration updated in memory"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
