from app.plugins.anpr.interfaces import IPlateDetector, IOCR
from app.plugins.anpr.detector import GenericYOLOPlateDetector, IndianYOLOPlateDetector
from app.plugins.anpr.providers.easyocr_provider import EasyOCRProvider
from app.plugins.anpr.providers.paddle_provider import PaddleOCRProvider
from app.plugins.anpr.providers.awiros_provider import AwirosOCRProvider
from app.plugins.anpr.config_parser import anpr_app_config
from loguru import logger

class ANPRFactory:
    """
    Factory for dependency injection of Plate Detectors and OCR wrappers based on config.yaml.
    """
    @staticmethod
    def get_plate_detector() -> IPlateDetector:
        provider = anpr_app_config.plate_detector.provider.lower()
        model_path = anpr_app_config.plate_detector.model_path
        conf_thresh = anpr_app_config.plate_detector.confidence_threshold
        
        if provider == "indian_yolo":
            logger.info("Injecting IndianYOLOPlateDetector")
            return IndianYOLOPlateDetector(model_path=model_path, conf_threshold=conf_thresh)
        else:
            logger.info("Injecting GenericYOLOPlateDetector")
            return GenericYOLOPlateDetector(model_path=model_path, conf_threshold=conf_thresh)
            
    @staticmethod
    def get_ocr_engine() -> IOCR:
        provider = anpr_app_config.ocr.provider.lower()
        use_gpu = anpr_app_config.ocr.use_gpu

        if provider in ("fast_plate", "fastplate", "fast-plate-ocr"):
            logger.info("Injecting FastPlateOCRProvider (plate-specialized ONNX OCR)")
            try:
                from app.plugins.anpr.providers.fastplate_provider import FastPlateOCRProvider
                engine = FastPlateOCRProvider(
                    model_name=anpr_app_config.ocr.fast_plate_model,
                    use_gpu=use_gpu
                )
                if engine.recognizer is not None:
                    return engine
                logger.error("fast-plate-ocr unavailable, falling back to EasyOCR")
            except Exception as e:
                logger.error(f"Failed to load FastPlateOCRProvider: {e}")

        if provider == "easyocr":
            logger.info("Injecting EasyOCRProvider for high accuracy Indian Plates")
            try:
                return EasyOCRProvider(use_gpu=use_gpu)
            except Exception as e:
                logger.error(f"Failed to load EasyOCRProvider: {e}")
        
        if provider == "awiros":
            logger.info("Attempting to inject AwirosOCRProvider")
            try:
                return AwirosOCRProvider(
                    local_model_path=anpr_app_config.ocr.local_model_path,
                    download_if_missing=anpr_app_config.ocr.download_if_missing,
                    use_gpu=use_gpu
                )
            except Exception as e:
                logger.error(f"Failed to load AwirosOCRProvider: {e}")
        
        # Default easyocr or paddle fallback
        logger.info("Defaulting to EasyOCRProvider")
        return EasyOCRProvider(use_gpu=use_gpu)
