import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from app.engine.base import FrameData


@dataclass
class FrameJob:
    """One frame's analytics work, handed from the GStreamer probe thread."""
    frame_data: FrameData
    # Raw detections payload for the Redis message, prebuilt as plain dicts.
    det_payload: List[Dict[str, Any]] = field(default_factory=list)
    enqueued_at: float = 0.0


class AnalyticsDispatcher:
    """
    Runs plugin analytics OFF the GStreamer streaming thread.

    - Per-camera mailbox of size 1 (latest frame wins): the probe never
      blocks and a slow plugin can only ever delay its own camera.
    - Each camera is processed strictly serially (plugin/tracker state is
      per-camera), while different cameras run in parallel on a thread pool.
      cv2 / onnxruntime / torch release the GIL, so workers use real cores.
    - Plugins whose class sets thread_safe=False execute under a per-plugin
      lock (their instance state is shared across cameras).
    - Publishes the same Redis payload the inline probe used to publish, so
      every downstream consumer (backend, UI, DB, alerts) is unchanged.
    """

    def __init__(
        self,
        engine,
        publish: Callable[[str, Dict[str, Any]], None],
        workers: Optional[int] = None,
    ):
        self.engine = engine
        self.publish = publish

        if workers is None:
            workers = int(os.getenv("ANALYTICS_WORKERS", "0")) or max(
                2, (os.cpu_count() or 8) - 2
            )
        self.pool = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="analytics"
        )
        # Blocking I/O (snapshot writes, DB lookups) that a plugin does not
        # want on an analytics worker. Nothing routes here yet — PPE snapshot
        # writes and the visitor DB match still run on their own threads — so
        # treat it as available capacity, not as something already in use.
        self.io_pool = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="analytics-io"
        )

        self._lock = threading.Lock()
        self._slots: Dict[str, FrameJob] = {}   # camera_id -> latest job
        self._busy: set = set()                 # cameras with an active worker

        # Metrics (read by the stats logger; written by workers/probe)
        self.drops: Dict[str, int] = {}
        self.processed: Dict[str, int] = {}
        self.submit_failures: Dict[str, int] = {}
        self.worker_ms_ema: Dict[str, float] = {}
        self._stats_stop = threading.Event()
        self._stats_thread = threading.Thread(
            target=self._stats_loop, daemon=True, name="analytics-stats"
        )
        self._stats_thread.start()

        logger.info(f"AnalyticsDispatcher started with {workers} workers.")

    # ------------------------------------------------------------------ #
    # Probe-side API (GStreamer streaming thread — must never block)
    # ------------------------------------------------------------------ #
    def submit(self, job: FrameJob) -> None:
        job.enqueued_at = time.perf_counter()
        cam = job.frame_data.camera_id
        with self._lock:
            if cam in self._slots:
                self.drops[cam] = self.drops.get(cam, 0) + 1
            self._slots[cam] = job
            if cam not in self._busy:
                self._busy.add(cam)
                try:
                    self.pool.submit(self._run_camera, cam)
                except Exception as exc:
                    # ThreadPoolExecutor spawns workers lazily, so submit()
                    # raises under thread/fd exhaustion and after shutdown.
                    # _busy is otherwise only cleared inside _run_camera, so
                    # leaving it set here would mark the camera permanently
                    # busy: no worker is ever scheduled again and it silently
                    # runs zero plugins for the rest of the process.
                    self._busy.discard(cam)
                    self._slots.pop(cam, None)
                    self.submit_failures[cam] = self.submit_failures.get(cam, 0) + 1
                    if self.submit_failures[cam] in (1, 10) or \
                            self.submit_failures[cam] % 500 == 0:
                        logger.error(
                            f"[{cam}] could not schedule analytics "
                            f"({self.submit_failures[cam]}x): {exc}"
                        )

    # ------------------------------------------------------------------ #
    # Worker side
    # ------------------------------------------------------------------ #
    def _run_camera(self, cam: str) -> None:
        while True:
            with self._lock:
                job = self._slots.pop(cam, None)
                if job is None:
                    self._busy.discard(cam)
                    return
            try:
                self._process(job)
            except Exception as exc:
                logger.error(f"[{cam}] analytics worker error: {exc}")

    def _process(self, job: FrameJob) -> None:
        cam = job.frame_data.camera_id
        t0 = time.perf_counter()

        events = self.engine.run_plugins(job.frame_data)

        from core.utils import clean_numpy
        payload = {
            "camera_id": cam,
            "sensor": {"id": cam},
            "detections": job.det_payload,
            "events": clean_numpy(events) if events else {},
            "timestamp": job.frame_data.timestamp,
            "fps": 30.0,
        }
        try:
            self.publish(cam, payload)
        except Exception as exc:
            logger.error(f"[{cam}] analytics publish error: {exc}")

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        prev = self.worker_ms_ema.get(cam, elapsed_ms)
        self.worker_ms_ema[cam] = prev * 0.9 + elapsed_ms * 0.1
        self.processed[cam] = self.processed.get(cam, 0) + 1
        if elapsed_ms > 250.0:
            logger.warning(
                f"[{cam}] slow analytics pass: {elapsed_ms:.0f}ms "
                f"(enabled plugins over budget — consider sampling)"
            )

    # ------------------------------------------------------------------ #
    # Metrics
    # ------------------------------------------------------------------ #
    def _stats_loop(self) -> None:
        prev_processed: Dict[str, int] = {}
        prev_drops: Dict[str, int] = {}
        while not self._stats_stop.wait(10.0):
            try:
                lines = []
                for cam in sorted(self.processed):
                    done = self.processed.get(cam, 0)
                    drop = self.drops.get(cam, 0)
                    d_done = done - prev_processed.get(cam, 0)
                    d_drop = drop - prev_drops.get(cam, 0)
                    prev_processed[cam] = done
                    prev_drops[cam] = drop
                    if d_done or d_drop:
                        lines.append(
                            f"{cam[:8]}: {d_done / 10.0:.1f}fps "
                            f"{self.worker_ms_ema.get(cam, 0):.1f}ms "
                            f"drop {d_drop}"
                        )
                if lines:
                    plugin_ms = getattr(self.engine, "plugin_ms_ema", {})
                    top = sorted(plugin_ms.items(), key=lambda kv: -kv[1])[:4]
                    top_txt = ", ".join(f"{n.replace('Plugin','')} {v:.1f}ms" for n, v in top)
                    logger.info(
                        "[analytics] " + " | ".join(lines)
                        + (f" || slowest plugins: {top_txt}" if top else "")
                    )
            except Exception:
                pass

    def stop(self) -> None:
        self._stats_stop.set()
        self.pool.shutdown(wait=False)
        self.io_pool.shutdown(wait=False)
