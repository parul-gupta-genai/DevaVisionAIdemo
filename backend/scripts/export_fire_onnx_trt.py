import argparse
import os
import sys
import subprocess
from pathlib import Path


def export_fire_model(weights_path: str, output_dir: str, build_trt: bool = False):
    """
    Export PyTorch fire detection model (best.pt) to ONNX format.
    Optionally calls trtexec to build a TensorRT FP16 engine.
    """
    weights = Path(weights_path)
    if not weights.is_file():
        print(f"[ERROR] Source weights file not found at: {weights_path}")
        sys.exit(1)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = out_dir / "best.onnx"

    print("==================================================")
    print(" DE-VAVISION AI — FIRE MODEL ONNX/TENSORRT EXPORT ")
    print("==================================================")
    print(f" Source Weights : {weights.resolve()}")
    print(f" Target ONNX    : {onnx_path.resolve()}")

    try:
        from ultralytics import YOLO
        print("\n[INFO] Loading YOLO fire model...")
        model = YOLO(str(weights))

        print("[INFO] Exporting to ONNX format (imgsz=640, dynamic=False, half=False)...")
        exported_path = model.export(
            format="onnx",
            imgsz=640,
            dynamic=False,
            simplify=True,
            opset=12,
        )
        print(f"[SUCCESS] ONNX model exported successfully to: {exported_path}")

    except Exception as exc:
        print(f"[ERROR] Failed to export model to ONNX: {exc}")
        sys.exit(1)

    # TensorRT Engine compilation if requested and trtexec is available
    if build_trt:
        trt_engine_path = out_dir / "best_fp16.engine"
        print(f"\n[INFO] Compiling TensorRT FP16 engine to: {trt_engine_path}")
        trtexec_cmd = [
            "trtexec",
            f"--onnx={exported_path}",
            f"--saveEngine={trt_engine_path}",
            "--fp16",
            "--workspace=2048",
        ]
        try:
            res = subprocess.run(trtexec_cmd, capture_output=True, text=True)
            if res.returncode == 0:
                print(f"[SUCCESS] TensorRT engine compiled: {trt_engine_path}")
            else:
                print(f"[WARN] trtexec failed or not found on system PATH.")
                print(res.stderr[:500])
        except FileNotFoundError:
            print("[WARN] 'trtexec' executable not found on PATH. Run engine build on target Jetson device.")

    print("\n[INFO] Export process completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export DevaVisionAI Fire Model to ONNX/TensorRT")
    parser.add_argument(
        "--weights",
        type=str,
        default="runs_fire/train/weights/best.pt",
        help="Path to trained PyTorch weights file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="runs_fire/train/weights",
        help="Directory to save exported ONNX and engine files",
    )
    parser.add_argument(
        "--build-trt",
        action="store_true",
        help="Compile TensorRT FP16 engine using trtexec if available",
    )

    args = parser.parse_args()
    export_fire_model(args.weights, args.output_dir, args.build_trt)
