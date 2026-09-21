"""
Unit tests for YoloFireDetector (local inference, candidate creation, class filtering).
"""

from unittest.mock import MagicMock
import numpy as np
import pytest

from app.plugins.fire.detector import FIRE, SMOKE
from app.plugins.fire.yolo_fire_detector import YoloFireDetector


def test_yolo_fire_detector_infer_local_success():
    detector = YoloFireDetector()
    detector._available = True

    # Mock Ultralytics YOLO model output
    mock_box_fire = MagicMock()
    mock_box_fire.conf = [0.85]
    mock_box_fire.cls = [0]
    mock_box_fire.xyxy = [np.array([10.0, 20.0, 100.0, 200.0])]

    mock_box_smoke = MagicMock()
    mock_box_smoke.conf = [0.75]
    mock_box_smoke.cls = [3]
    mock_box_smoke.xyxy = [np.array([50.0, 60.0, 150.0, 250.0])]

    mock_result = MagicMock()
    mock_result.boxes = [mock_box_fire, mock_box_smoke]
    mock_result.names = {0: "fire", 1: "light", 2: "no-fire", 3: "smoke"}

    detector._model = MagicMock(return_value=[mock_result])

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    candidates = detector._infer_local(frame)

    assert len(candidates) == 2
    c_fire = candidates[0]
    assert c_fire.kind == FIRE
    assert c_fire.score == 0.85
    assert c_fire.bbox == [10, 20, 100, 200]

    c_smoke = candidates[1]
    assert c_smoke.kind == SMOKE
    assert c_smoke.score == 0.75
    assert c_smoke.bbox == [50, 60, 150, 250]


def test_yolo_fire_detector_ignores_no_fire():
    detector = YoloFireDetector()
    detector._available = True

    mock_box_nofire = MagicMock()
    mock_box_nofire.conf = [0.90]
    mock_box_nofire.cls = [2]
    mock_box_nofire.xyxy = [np.array([10.0, 20.0, 100.0, 200.0])]

    mock_result = MagicMock()
    mock_result.boxes = [mock_box_nofire]
    mock_result.names = {0: "fire", 1: "light", 2: "no-fire", 3: "smoke"}

    detector._model = MagicMock(return_value=[mock_result])

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    candidates = detector._infer_local(frame)

    assert len(candidates) == 0
