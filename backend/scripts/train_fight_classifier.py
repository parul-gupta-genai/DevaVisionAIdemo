"""
Train a fight/violence video classifier on the RLVS-style dataset uploaded
into backend/dataset_fight/{train,val,test}/{Violence,NonViolence}/.

NOTE — WHY THIS ISN'T A YOLO SCRIPT (unlike train_helmet_yolo.py and
train_vehicle_yolo.py next to this file): YOLO detects WHERE objects are in
a single frame — it has no notion of time. "Is this a fight" isn't a
where-question about one frame, it's a WHAT-IS-HAPPENING-OVER-TIME
question — the same two people standing close together is either a fight
or two friends talking, and the only way to tell is motion across several
frames. That's a video-classification problem, not object detection, so
YOLO genuinely doesn't apply here regardless of GPU access — this
frame-sampling + CNN + temporal pooling approach (below) is the correct
architecture family for this task, not a compromise like the crop-based
classifiers helmet/vehicle detection used.

WHY THIS APPROACH (not a full 3D-CNN like the original RWF-2000 repo uses):
  - The RWF-2000 authors' own notebooks train a "Flow Gated Network" that
    needs optical flow pre-computed for every frame of every clip — heavy
    to preprocess and slow to train.
  - Instead, this script uses frame-sampling + a pretrained 2D CNN backbone
    (MobileNetV2, ImageNet-pretrained) run per sampled frame, average-pooled
    over time, and fed into a small classifier head. This is the standard
    lightweight baseline for exactly this kind of short-clip violence
    dataset, trains in minutes-to-an-hour even on a modest GPU, and is easy
    to export/run at inference time inside DevaVisionAI's existing Python
    plugin loop (no separate optical-flow pipeline needed).

WHAT THIS REPLACES / HOW IT FITS THE EXISTING FightDetectionPlugin:
  - backend/app/plugins/fight/{dynamics.py,rules.py} currently decide
    "fight" purely from person-bbox motion/proximity heuristics — no
    learned model at all. That's why real scuffles vs. two people just
    walking close together get confused.
  - The sandbox instead shipped fight_classifier.joblib (a Random Forest on
    handcrafted motion/optical-flow features — see extract_fight_features.py
    and train_fight_ml.py), already wired into adapter.py, because PyTorch
    couldn't run in that environment. This script is the upgrade path: a
    real learned CNN+temporal model instead of handcrafted features, using
    the SAME 2000-video dataset. Once trained, swap ml_classifier.py's
    FightMLClassifier for one that loads this script's output instead — the
    adapter.py integration (frame buffering, confirm/veto thresholds) stays
    the same, only the model underneath changes.

REQUIREMENTS (run on your own GPU machine, not this sandbox — no GPU here):
    pip install torch torchvision opencv-python

USAGE:
    python train_fight_classifier.py --epochs 15
    python train_fight_classifier.py --epochs 15 --frames-per-clip 16 --device 0
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset_fight"
OUTPUT_DIR = BASE_DIR / "runs_fight_classifier"
CLASSES = ["NonViolence", "Violence"]  # index 0 / 1 — keep this order, it's baked into labels below


def sample_frames(video_path: Path, n_frames: int):
    """Uniformly sample n_frames RGB frames from a video, resized to 224x224."""
    cap = cv2.VideoCapture(str(video_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return None

    idxs = np.linspace(0, max(total - 1, 0), n_frames).astype(int)
    frames = []
    idx_set = set(idxs.tolist())
    i = 0
    while cap.isOpened() and len(frames) < n_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if i in idx_set:
            frame = cv2.resize(frame, (224, 224))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(frame)
        i += 1
    cap.release()

    if not frames:
        return None
    # pad by repeating the last frame if the video was shorter than expected
    while len(frames) < n_frames:
        frames.append(frames[-1])
    return np.stack(frames[:n_frames])  # (n_frames, 224, 224, 3) uint8


def build_manifest(split: str):
    """List (video_path, label_idx) pairs for a split."""
    items = []
    for label_idx, cls in enumerate(CLASSES):
        cls_dir = DATASET_DIR / split / cls
        if not cls_dir.exists():
            continue
        for f in sorted(cls_dir.iterdir()):
            if f.suffix.lower() in (".mp4", ".avi"):
                items.append((f, label_idx))
    return items


class ClipDataset:
    """Minimal on-the-fly dataset: reads+samples frames per __getitem__ call.
    (Not pre-caching to disk — 2000 clips x 16 frames x 224x224x3 would be
    several GB; sampling per-epoch is slower but keeps disk/RAM usage low.)
    """

    def __init__(self, split: str, frames_per_clip: int):
        self.items = build_manifest(split)
        self.frames_per_clip = frames_per_clip
        if not self.items:
            raise RuntimeError(f"No videos found for split '{split}' under {DATASET_DIR}")

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        path, label = self.items[i]
        frames = sample_frames(path, self.frames_per_clip)
        if frames is None:
            # unreadable clip — substitute a black clip rather than crashing
            # a whole training run over one bad file; log so it can be
            # investigated/removed from the dataset afterwards.
            print(f"[warn] could not read frames from {path}, using blank clip")
            frames = np.zeros((self.frames_per_clip, 224, 224, 3), dtype=np.uint8)
        return frames, label


def train(epochs: int, frames_per_clip: int, batch_size: int, lr: float, device_arg: str | None):
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader
    from torchvision import models, transforms

    device = torch.device(
        f"cuda:{device_arg}" if device_arg not in (None, "cpu") and torch.cuda.is_available()
        else "cpu"
    )
    print(f"Using device: {device}")

    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

    def collate(batch):
        clips, labels = zip(*batch)
        clips = np.stack(clips).astype(np.float32) / 255.0  # (B, T, H, W, 3)
        clips = torch.from_numpy(clips).permute(0, 1, 4, 2, 3)  # (B, T, 3, H, W)
        B, T = clips.shape[0], clips.shape[1]
        clips = clips.view(B * T, 3, 224, 224)
        clips = torch.stack([normalize(c) for c in clips])
        clips = clips.view(B, T, 3, 224, 224)
        return clips, torch.tensor(labels, dtype=torch.long)

    train_ds = ClipDataset("train", frames_per_clip)
    val_ds = ClipDataset("val", frames_per_clip)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                               collate_fn=collate, num_workers=2)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                             collate_fn=collate, num_workers=2)

    # Backbone: ImageNet-pretrained MobileNetV2, used as a per-frame feature
    # extractor (its classifier head is dropped). Frozen for the first pass —
    # only the temporal head is trained — which is fast and avoids overfitting
    # a 2000-clip dataset with a full CNN fine-tune.
    backbone = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)
    backbone.classifier = nn.Identity()
    for p in backbone.parameters():
        p.requires_grad = False
    backbone = backbone.to(device).eval()

    class TemporalHead(nn.Module):
        def __init__(self, feat_dim=1280, hidden=256, n_classes=2):
            super().__init__()
            self.gru = nn.GRU(feat_dim, hidden, batch_first=True, bidirectional=True)
            self.fc = nn.Sequential(
                nn.Linear(hidden * 2, hidden), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(hidden, n_classes),
            )

        def forward(self, feats):  # feats: (B, T, feat_dim)
            out, _ = self.gru(feats)
            pooled = out.mean(dim=1)
            return self.fc(pooled)

    head = TemporalHead().to(device)
    optimizer = torch.optim.Adam(head.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0

    for epoch in range(1, epochs + 1):
        head.train()
        total, correct, running_loss = 0, 0, 0.0
        for clips, labels in train_loader:
            clips, labels = clips.to(device), labels.to(device)
            B, T = clips.shape[0], clips.shape[1]
            with torch.no_grad():
                feats = backbone(clips.view(B * T, 3, 224, 224)).view(B, T, -1)
            optimizer.zero_grad()
            logits = head(feats)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * B
            correct += (logits.argmax(1) == labels).sum().item()
            total += B

        train_acc = correct / total
        train_loss = running_loss / total

        head.eval()
        v_total, v_correct = 0, 0
        with torch.no_grad():
            for clips, labels in val_loader:
                clips, labels = clips.to(device), labels.to(device)
                B, T = clips.shape[0], clips.shape[1]
                feats = backbone(clips.view(B * T, 3, 224, 224)).view(B, T, -1)
                logits = head(feats)
                v_correct += (logits.argmax(1) == labels).sum().item()
                v_total += B
        val_acc = v_correct / v_total

        print(f"epoch {epoch}/{epochs}  train_loss={train_loss:.4f}  "
              f"train_acc={train_acc:.3f}  val_acc={val_acc:.3f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(
                {"head_state_dict": head.state_dict(), "classes": CLASSES,
                 "frames_per_clip": frames_per_clip},
                OUTPUT_DIR / "fight_classifier_best.pt",
            )

    print(f"\nBest val_acc: {best_val_acc:.3f}")
    print(f"Weights saved to: {OUTPUT_DIR / 'fight_classifier_best.pt'}")
    print(
        "\nNOTE: this saves only the temporal head's weights — the MobileNetV2 "
        "backbone is standard torchvision ImageNet weights, re-loaded fresh at "
        "inference time (see fire plugin's yolo_fire_detector.py for the "
        "pattern of loading a model once at plugin init and reusing it)."
    )


def main():
    parser = argparse.ArgumentParser(description="Train fight/violence video classifier")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--frames-per-clip", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--device", type=str, default=None, help="'0' for GPU 0, 'cpu' for CPU")
    args = parser.parse_args()
    train(args.epochs, args.frames_per_clip, args.batch_size, args.lr, args.device)


if __name__ == "__main__":
    main()

# --- Integration note for backend/app/plugins/fight/ ---
# At inference time: keep a rolling buffer of the last N frames per camera
# (already similar buffering likely exists for the motion heuristics in
# dynamics.py). Every ~1s, sample `frames_per_clip` frames from that buffer,
# run them through MobileNetV2 + the trained TemporalHead to get a violence
# probability. Combine with the existing rule-based signal conservatively —
# e.g. only raise a FIGHT_DETECTED event when BOTH the motion heuristic AND
# the classifier agree, or use the classifier score to gate/suppress
# heuristic false positives (two people walking closely but the classifier
# score is low). Don't let the classifier fully replace the heuristic on
# day one — validate its false-positive/negative rate on real camera
# footage first.
