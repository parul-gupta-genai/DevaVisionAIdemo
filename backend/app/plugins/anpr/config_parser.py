import yaml
from pathlib import Path
from pydantic import BaseModel
from typing import List

class OCRConfig(BaseModel):
    provider: str = "awiros"
    local_model_path: str = "models/awiros"
    download_if_missing: bool = True
    use_gpu: bool = False
    confidence_threshold: float = 0.55
    fallback_provider: str = "paddle"
    fast_plate_model: str = "cct-s-v1-global-model"

class PlateDetectorConfig(BaseModel):
    provider: str = "yolo"
    model_path: str = "plate_yolo.pt"
    confidence_threshold: float = 0.5

class ValidationConfig(BaseModel):
    smart_repair_enabled: bool = True
    repair_confidence_threshold: float = 0.85
    strict: bool = True
    format_strategies: List[str] = ["private", "commercial"]

class FusionConfig(BaseModel):
    min_observations: int = 2
    track_timeout_seconds: float = 3.0
    weighted_voting: bool = True

class EnhancementConfig(BaseModel):
    clahe_clip_limit: float = 2.0
    denoise_h: int = 30
    quality_threshold: float = 0.75

class ANPRConfigModel(BaseModel):
    ocr: OCRConfig
    plate_detector: PlateDetectorConfig
    validation: ValidationConfig
    fusion: FusionConfig
    enhancement: EnhancementConfig

def load_anpr_config(config_path: str = "config.yaml") -> ANPRConfigModel:
    base_path = Path(__file__).parent
    full_path = base_path / config_path
    
    if not full_path.exists():
        # Fallback to defaults if file doesn't exist yet
        return ANPRConfigModel(
            ocr=OCRConfig(),
            plate_detector=PlateDetectorConfig(),
            validation=ValidationConfig(),
            fusion=FusionConfig(),
            enhancement=EnhancementConfig()
        )
        
    with open(full_path, 'r') as f:
        data = yaml.safe_load(f)
    return ANPRConfigModel(**data)

anpr_app_config = load_anpr_config()
