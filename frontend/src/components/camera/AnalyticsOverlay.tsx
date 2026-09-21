import React, { useEffect, useRef } from 'react';
import { useCameraStateStore } from '@/store/useCameraStateStore';
import { computeContainViewport } from '@/utils/viewport';
import { webrtcStreamManager } from '@/services/webrtcStreamManager';

interface AnalyticsOverlayProps {
  cameraId: string;
}

const CLASS_COLORS: Record<number, string> = {
  0: '#10B981', // Person -> Emerald Green
  1: '#F59E0B', // Bicycle / PPE -> Amber
  2: '#3B82F6', // Car -> Blue
  3: '#8B5CF6', // Motorcycle -> Purple
  5: '#EC4899', // Bus -> Pink
  7: '#06B6D4', // Truck -> Cyan
};

const CLASS_NAMES: Record<number, string> = {
  0: 'Person',
  1: 'Bicycle',
  2: 'Car',
  3: 'Motorcycle',
  5: 'Bus',
  7: 'Truck',
};

export const AnalyticsOverlay: React.FC<AnalyticsOverlayProps> = ({ cameraId }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const telemetry = useCameraStateStore((state) => state.states[cameraId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const parent = canvas.parentElement;
    if (!parent) return;

    const width = parent.clientWidth;
    const height = parent.clientHeight;

    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    ctx.clearRect(0, 0, width, height);

    if (!telemetry) return;

    const detections = telemetry.detections || [];
    const events = telemetry.events || {};

    // If all plugins are turned off, keep video completely clean with no boxes or lines
    const hasActivePlugins = Object.entries(events).some(([_, evts]) => 
      Array.isArray(evts) ? evts.length > 0 : !!evts
    );
    if (!hasActivePlugins) {
      return;
    }

    // Never draw boxes over a video that is not currently showing live
    // frames. readyState alone is not enough: once a MediaStream has decoded
    // one frame it stays at HAVE_ENOUGH_DATA even after the publisher dies,
    // which is exactly how detections ended up floating over a frozen black
    // tile. The stream manager's decoded-frame watchdog is the real signal.
    const videoEl = parent.querySelector('video') as HTMLVideoElement | null;
    if (videoEl && videoEl.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      return;
    }
    if (!webrtcStreamManager.isLive(cameraId)) {
      return;
    }

    // Exact aspect-ratio viewport computation (matches object-contain) —
    // shared with CountingLineEditor so drawn lines land exactly where
    // events render.
    const { offsetX, offsetY, scaleX, scaleY } = computeContainViewport(width, height, videoEl);

    const mapX = (x: number) => offsetX + x * scaleX;
    const mapY = (y: number) => offsetY + y * scaleY;

    // 3. Render AI Object Bounding Boxes & Tracking IDs (generic, drawn first
    // so any plugin-confirmed overlay below always renders on top of it)
    for (const det of detections) {
      const { bbox, class_id = 0, confidence = 1.0, track_id } = det;
      if (!bbox || bbox.length < 4) continue;

      let [x1, y1, x2, y2] = bbox;
      if (x2 < x1 || y2 < y1) {
        x2 = x1 + x2;
        y2 = y1 + y2;
      }

      const screenX = mapX(x1);
      const screenY = mapY(y1);
      const screenW = (x2 - x1) * scaleX;
      const screenH = (y2 - y1) * scaleY;

      if (screenW <= 0 || screenH <= 0) continue;

      const rawLabel = det.label || det.class_name || CLASS_NAMES[class_id] || 'Object';
      const labelLower = rawLabel.toLowerCase();
      const isFire = labelLower.includes('fire');
      const isSmoke = labelLower.includes('smoke');

      const color = isFire
        ? '#EF4444'
        : isSmoke
        ? '#F97316'
        : (CLASS_COLORS[class_id] || '#10B981');

      const labelName = rawLabel;
      const displayConf = Math.min(100, Math.max(50, Math.round(confidence * 100)));
      const labelText = track_id !== undefined && track_id !== null
        ? `${labelName} #${track_id} ${displayConf}%`
        : `${labelName} ${displayConf}%`;

      // Bounding Box Rect
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(screenX, screenY, screenW, screenH);

      // Target Subtle Fill
      ctx.fillStyle = `${color}14`;
      ctx.fillRect(screenX, screenY, screenW, screenH);

      // Label Tag Background
      ctx.font = 'bold 11px Inter, sans-serif';
      const textMetrics = ctx.measureText(labelText);
      const tagHeight = 16;
      const tagWidth = textMetrics.width + 8;
      const tagY = Math.max(offsetY, screenY - tagHeight);

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.roundRect(screenX, tagY, tagWidth, tagHeight, [3, 3, 0, 0]);
      ctx.fill();

      // Label Text
      ctx.fillStyle = '#000000';
      ctx.fillText(labelText, screenX + 4, tagY + 12);
    }

    // 4. Render Plugin Custom Drawings ONLY for actively enabled plugins
    // (Fixed coordinates). Drawn LAST so a plugin's confirmed event (fire,
    // smoke, PPE violation, ANPR plate, zone) is always visible on top of
    // any generic bounding box from section 3 above, even if both land on
    // the same screen area.
    for (const [pluginName, pluginEvents] of Object.entries(events)) {
      if (!Array.isArray(pluginEvents) || pluginEvents.length === 0) continue;

      for (const evt of pluginEvents) {
        const drawings = evt?.metadata?.drawings || [];
        for (const d of drawings) {
          if (d.type === 'line' && d.coords && d.coords.length >= 2) {
            const [[x1, y1], [x2, y2]] = d.coords;
            const sx1 = mapX(x1);
            const sy1 = mapY(y1);
            const sx2 = mapX(x2);
            const sy2 = mapY(y2);

            ctx.save();
            ctx.shadowColor = `rgba(${d.color?.join(',') || '0,240,255'}, 0.8)`;
            ctx.shadowBlur = 6;
            ctx.beginPath();
            ctx.moveTo(sx1, sy1);
            ctx.lineTo(sx2, sy2);
            ctx.strokeStyle = `rgb(${d.color?.join(',') || '0,240,255'})`;
            ctx.lineWidth = (d.thickness || 2) + 0.5;
            ctx.stroke();
            ctx.restore();
          } else if (d.type === 'rect' && d.coords && d.coords.length >= 4) {
            // coords: [x1, y1, x2, y2] in video pixel space (e.g. ANPR plate box)
            const [x1, y1, x2, y2] = d.coords;
            const rx = mapX(x1);
            const ry = mapY(y1);
            const rw = (x2 - x1) * scaleX;
            const rh = (y2 - y1) * scaleY;
            if (rw > 0 && rh > 0) {
              ctx.save();
              ctx.strokeStyle = `rgb(${d.color?.join(',') || '255,200,0'})`;
              ctx.lineWidth = (d.thickness || 2) + 0.5;
              ctx.shadowColor = `rgba(${d.color?.join(',') || '255,200,0'}, 0.6)`;
              ctx.shadowBlur = 4;
              ctx.strokeRect(rx, ry, rw, rh);
              ctx.restore();
            }
          } else if (d.type === 'poly' && d.coords && d.coords.length >= 3) {
            // coords: [[x, y], ...] polygon in video pixel space
            // (parking bays, restriction/intrusion zones)
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(mapX(d.coords[0][0]), mapY(d.coords[0][1]));
            for (let i = 1; i < d.coords.length; i++) {
              ctx.lineTo(mapX(d.coords[i][0]), mapY(d.coords[i][1]));
            }
            ctx.closePath();
            const rgb = d.color?.join(',') || '0,255,0';
            ctx.fillStyle = `rgba(${rgb}, ${d.opacity ?? 0.2})`;
            ctx.fill();
            ctx.strokeStyle = `rgb(${rgb})`;
            ctx.lineWidth = (d.thickness || 2) + 0.5;
            ctx.shadowColor = `rgba(${rgb}, 0.6)`;
            ctx.shadowBlur = 4;
            ctx.stroke();
            ctx.restore();
          } else if (d.type === 'text' && d.coords && d.coords.length >= 2 && d.text) {
            // coords: [x, y] anchor in video pixel space (e.g. plate number)
            const tx = mapX(d.coords[0]);
            const ty = mapY(d.coords[1]);
            ctx.save();
            ctx.font = `bold ${Math.max(12, Math.round(14 * (d.scale || 1)))}px Inter, sans-serif`;
            const metrics = ctx.measureText(d.text);
            const pad = 4;
            const boxH = Math.max(16, Math.round(16 * (d.scale || 1)));
            ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
            ctx.beginPath();
            ctx.roundRect(tx - pad, ty - boxH, metrics.width + pad * 2, boxH + pad, 3);
            ctx.fill();
            ctx.fillStyle = `rgb(${d.color?.join(',') || '255,255,255'})`;
            ctx.fillText(d.text, tx, ty - 3);
            ctx.restore();
          }
        }
      }
    }
  }, [telemetry]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none z-10"
    />
  );
};
