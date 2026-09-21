import cv2
import numpy as np

def enhance_day_night_frame(image: np.ndarray, low_light_threshold: float = 70.0) -> np.ndarray:
    """
    Auto-adaptive Day & Night Image Enhancement.
    Detects low-light/night conditions automatically and applies CLAHE in LAB space
    and gamma correction to boost AI model detection accuracy in dark scenes.
    """
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        return image

    try:
        # Convert to YUV / LAB to check mean luminance
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        mean_luminance = l_channel.mean()

        # If daytime / normal light, return original frame (0 latency overhead)
        if mean_luminance >= low_light_threshold:
            return image

        # Low-light / Night-time optimization:
        # 1. Apply CLAHE on L (Luminance) channel
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl_channel = clahe.apply(l_channel)

        # 2. Merge enhanced L channel back with A and B channels
        merged_lab = cv2.merge((cl_channel, a_channel, b_channel))
        enhanced_bgr = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)

        # 3. Apply subtle gamma correction for deep shadow visibility
        gamma = 1.3
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        gamma_corrected = cv2.LUT(enhanced_bgr, table)

        return gamma_corrected
    except Exception:
        return image
