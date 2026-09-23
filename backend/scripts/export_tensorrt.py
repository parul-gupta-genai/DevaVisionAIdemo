"""
TensorRT Export Utility for DevaVisionAI.

Converts YOLO11 / YOLOv10 / YOLOv8 .pt weights to a TensorRT .engine file
for maximum GPU inference throughput.

WHY TENSORRT:
  PyTorch YOLO11n (FP32) :  ~12ms / frame on RTX GPU
  PyTorch YOLO11n (FP16) :  ~7ms  / frame on RTX GPU
  TensorRT YOLO11n (FP16):  ~2-4ms / frame on RTX GPU   <- 3-5x faster

HOW TO USE:
  # Export fire detection model to TensorRT FP16:
  python scripts/export_tensorrt.py --plugin fire --half

  # Export helmet model:
  python scripts/export_tensorrt.py --plugin helmet --half

  # Custom model path:
  python scripts/export_tensorrt.py --model /path/to/best.pt --out /path/to/fire.engine

AFTER EXPORT -- add to .env:
  USE_TENSORRT=true
  TRT_ENGINE_FIRE=/path/to/fire.engine      # from --plugin fire
  TRT_ENGINE_FIGHT=/path/to/fight.engine    # from --plugin fight
  TRT_ENGINE_HELMET=/path/to/helmet.engine  # from --plugin helmet

REQUIREMENTS:
  pip install ultralytics tensorrt
  NVIDIA GPU + CUDA + TensorRT runtime installed
  (TensorRT is included with NVIDIA JetPack on Jetson devices)

NOTE: The .engine file is hardware-specific -- an engine built on an RTX 3080
      will NOT work on a Jetson Orin. Export on the deployment machine.
"""

import argparse
import os
import sys
from pathlib import Path

# -- Default model locations per plugin ---------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent

_PLUGIN_MODELS = {
    "fire":   _BACKEND_DIR / "runs_fire" / "train" / "weights" / "best.pt",
    "fight":  _BACKEND_DIR / "app" / "plugins" / "fight" / "fight_classifier_best.pt",
    "helmet": _BACKEND_DIR / "runs_helmet_yolo" / "train" / "weights" / "best.pt",
}

# Fallback local .pt files when runs_* doesn't exist yet
_PLUGIN_FALLBACKS = {
    "fire":   _BACKEND_DIR / "app" / "plugins" / "fire" / "fire_yolo.pt",
    "fight":  _BACKEND_DIR / "app" / "plugins" / "fight" / "fight_classifier_best.pt",
    "helmet": None,
}

# Output engine locations
_PLUGIN_ENGINE_PATHS = {
    "fire":   _BACKEND_DIR / "app" / "plugins" / "fire" / "fire.engine",
    "fight":  _BACKEND_DIR / "app" / "plugins" / "fight" / "fight.engine",
    "helmet": _BACKEND_DIR / "app" / "plugins" / "ppe"  / "helmet.engine",
}

# Env var names for .env instructions
_PLUGIN_ENV_VARS = {
    "fire":   "TRT_ENGINE_FIRE",
    "fight":  "TRT_ENGINE_FIGHT",
    "helmet": "TRT_ENGINE_HELMET",
}


def resolve_model(plugin: str, model_override: str = None) -> Path:
    """Find the best .pt file for the given plugin."""
    if model_override:
        p = Path(model_override)
        if not p.exists():
            raise FileNotFoundError(f"Model not found: {p}")
        return p

    primary = _PLUGIN_MODELS.get(plugin)
    if primary and primary.exists():
        return primary

    fallback = _PLUGIN_FALLBACKS.get(plugin)
    if fallback and fallback.exists():
        print(f"  [!] Primary model not found, using fallback: {fallback}")
        return fallback

    raise FileNotFoundError(
        f"No trained model found for plugin '{plugin}'.\n"
        f"  Expected: {primary}\n"
        f"  Run the training script first:\n"
        f"    python scripts/train_fire_dataset.py  (for fire)\n"
        f"    python scripts/train_helmet_yolo.py   (for helmet)\n"
        f"  Or pass --model /path/to/your.pt"
    )


def export_to_tensorrt(
    model_path: Path,
    output_path: Path,
    half: bool = True,
    imgsz: int = 640,
    batch: int = 1,
    workspace: int = 4,
) -> Path:
    """
    Export a YOLO .pt model to TensorRT .engine format.

    Args:
        model_path: Path to .pt weights file
        output_path: Desired output .engine file path
        half: Use FP16 (recommended for speed, requires GPU with FP16 support)
        imgsz: Input image size (must match training)
        batch: Batch size (1 for real-time streaming, 4+ for batch processing)
        workspace: TensorRT workspace memory in GB

    Returns:
        Path to the exported .engine file
    """
    try:
        from ultralytics import YOLO  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "ultralytics not installed. Run: pip install ultralytics"
        )

    try:
        import torch  # noqa: PLC0415
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA not available! TensorRT export requires an NVIDIA GPU.\n"
                "Check: nvidia-smi, nvcc --version, torch.cuda.is_available()"
            )
    except ImportError:
        raise ImportError("torch not installed. Run: pip install torch")

    print(f"\n{'='*60}")
    print(f"  TensorRT Export")
    print(f"{'='*60}")
    print(f"  Model  : {model_path}")
    print(f"  Output : {output_path}")
    print(f"  FP16   : {half}")
    print(f"  imgsz  : {imgsz}")
    print(f"  batch  : {batch}")
    print(f"  VRAM   : {workspace} GB workspace")
    print(f"{'='*60}\n")

    model = YOLO(str(model_path))

    # Export -- ultralytics handles TensorRT serialisation internally
    exported = model.export(
        format="engine",
        half=half,
        imgsz=imgsz,
        batch=batch,
        workspace=workspace,
        device=0,          # always GPU 0 for TRT export
        verbose=True,
    )

    exported_path = Path(exported) if exported else model_path.with_suffix(".engine")

    # Move to desired output path if different
    if exported_path.resolve() != output_path.resolve():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        exported_path.rename(output_path)
        print(f"\n  OK Engine moved to: {output_path}")
    else:
        print(f"\n  OK Engine saved at: {exported_path}")

    return output_path


def print_env_instructions(plugin: str, engine_path: Path) -> None:
    """Print .env configuration instructions after successful export."""
    env_var = _PLUGIN_ENV_VARS.get(plugin, "TRT_ENGINE_PATH")
    print(f"\n{'='*60}")
    print("  Next Steps -- add to your .env:")
    print(f"{'='*60}")
    print(f"  USE_TENSORRT=true")
    print(f"  {env_var}={engine_path.resolve()}")
    print(f"\n  Then restart the backend. You should see in the logs:")
    print(f"    TensorRT backend active for {plugin} plugin")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Export YOLO11/YOLOv10 model to TensorRT for DevaVisionAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python export_tensorrt.py --plugin fire --half
  python export_tensorrt.py --plugin helmet --half --imgsz 640
  python export_tensorrt.py --model my_model.pt --out fire.engine --half
        """
    )
    parser.add_argument(
        "--plugin", type=str, choices=["fire", "fight", "helmet"],
        help="Plugin to export (auto-resolves model path)"
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Explicit .pt model path (overrides --plugin model resolution)"
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="Output .engine path (default: plugin standard location)"
    )
    parser.add_argument(
        "--half", action="store_true", default=True,
        help="FP16 export (recommended, ~2x faster than FP32)"
    )
    parser.add_argument(
        "--fp32", action="store_true", default=False,
        help="FP32 export (slower, use if GPU does not support FP16)"
    )
    parser.add_argument(
        "--imgsz", type=int, default=640,
        help="Input image size (default: 640)"
    )
    parser.add_argument(
        "--batch", type=int, default=1,
        help="Batch size (default: 1 for real-time, 4+ for batch)"
    )
    parser.add_argument(
        "--workspace", type=int, default=4,
        help="TensorRT workspace memory in GB (default: 4)"
    )
    args = parser.parse_args()

    if not args.plugin and not args.model:
        parser.error("Provide --plugin (fire/fight/helmet) or --model /path/to/model.pt")

    use_half = args.half and not args.fp32

    plugin = args.plugin or "default"
    try:
        model_path = resolve_model(plugin, args.model)
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    if args.out:
        output_path = Path(args.out)
    elif args.plugin:
        output_path = _PLUGIN_ENGINE_PATHS[args.plugin]
    else:
        output_path = model_path.with_suffix(".engine")

    try:
        engine_path = export_to_tensorrt(
            model_path=model_path,
            output_path=output_path,
            half=use_half,
            imgsz=args.imgsz,
            batch=args.batch,
            workspace=args.workspace,
        )
        if args.plugin:
            print_env_instructions(args.plugin, engine_path)
    except RuntimeError as e:
        print(f"\nExport failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        raise


if __name__ == "__main__":
    main()
