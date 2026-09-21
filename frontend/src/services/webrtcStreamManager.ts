type StreamListener = (stream: MediaStream | null, error: string | null) => void;

interface StreamEntry {
  cameraId: string;
  pc: RTCPeerConnection | null;
  stream: MediaStream | null;
  refCount: number;
  listeners: Set<StreamListener>;
  isConnecting: boolean;
  cleanupTimer: ReturnType<typeof setTimeout> | null;
}

class WebRTCStreamManager {
  private entries = new Map<string, StreamEntry>();
  private readonly GRACE_PERIOD_MS = 45000; // Keep stream alive for 45s after unmount

  public subscribe(cameraId: string, listener: StreamListener): () => void {
    let entry = this.entries.get(cameraId);

    if (!entry) {
      entry = {
        cameraId,
        pc: null,
        stream: null,
        refCount: 0,
        listeners: new Set(),
        isConnecting: false,
        cleanupTimer: null,
      };
      this.entries.set(cameraId, entry);
    }

    if (entry.cleanupTimer) {
      clearTimeout(entry.cleanupTimer);
      entry.cleanupTimer = null;
    }

    entry.refCount++;
    entry.listeners.add(listener);

    if (entry.stream && entry.stream.active && entry.stream.getVideoTracks().length > 0) {
      listener(entry.stream, null);
    } else if (!entry.isConnecting) {
      this.connect(entry);
    }

    return () => {
      if (!entry) return;
      entry.listeners.delete(listener);
      entry.refCount = Math.max(0, entry.refCount - 1);

      if (entry.refCount === 0 && !entry.cleanupTimer) {
        entry.cleanupTimer = setTimeout(() => {
          this.destroyEntry(cameraId);
        }, this.GRACE_PERIOD_MS);
      }
    };
  }

  private async connect(entry: StreamEntry) {
    if (entry.isConnecting) return;
    entry.isConnecting = true;

    try {
      if (entry.pc) {
        try { entry.pc.close(); } catch (_) {}
      }

      const pc = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
      });
      entry.pc = pc;

      pc.addTransceiver('video', { direction: 'recvonly' });

      pc.ontrack = (event) => {
        let stream = (event.streams && event.streams[0]) ? event.streams[0] : null;
        if (!stream && event.track) {
          stream = new MediaStream([event.track]);
        }
        if (stream) {
          entry.stream = stream;
          entry.listeners.forEach(l => l(stream, null));
        }
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
      const whepUrls = [
        `/webrtc-stream/raw_${encodeURIComponent(entry.cameraId)}/whep`,
        `/webrtc-stream/${encodeURIComponent(entry.cameraId)}/whep`,
        `http://localhost:8189/raw_${encodeURIComponent(entry.cameraId)}/whep`,
        `http://localhost:8189/${encodeURIComponent(entry.cameraId)}/whep`,
        `http://${host}:8189/raw_${encodeURIComponent(entry.cameraId)}/whep`,
        `http://${host}:8189/${encodeURIComponent(entry.cameraId)}/whep`
      ];

      let response: Response | null = null;
      let lastErr: any = null;

      for (const url of whepUrls) {
        try {
          const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/sdp' },
            body: pc.localDescription?.sdp
          });
          if (res.ok) {
            response = res;
            break;
          }
        } catch (e) {
          lastErr = e;
        }
      }

      if (!response || !response.ok) {
        throw new Error(`Connecting stream (${entry.cameraId})...`);
      }

      const answerSdp = await response.text();
      await pc.setRemoteDescription(new RTCSessionDescription({
        type: 'answer',
        sdp: answerSdp
      }));

    } catch (err: any) {
      console.warn(`WebRTC Stream Manager [${entry.cameraId}]:`, err?.message || err);
      entry.listeners.forEach(l => l(null, err?.message || 'Connecting stream...'));
      // Auto-retry connection after 2.5s if still active
      if (entry.refCount > 0 && !entry.cleanupTimer) {
        setTimeout(() => {
          if (entry.refCount > 0 && (!entry.stream || !entry.stream.active)) {
            this.connect(entry);
          }
        }, 2500);
      }
    } finally {
      entry.isConnecting = false;
    }
  }

  public closeStream(cameraId: string) {
    this.destroyEntry(cameraId);
  }

  /**
   * Signals which camera is currently focused/expanded in the UI.
   * The edge can use this to prioritise full-framerate encoding for that camera.
   * No-op until the backend signaling endpoint is implemented.
   */
  public setFocused(_cameraId: string | null) {
    // Future: POST /api/cameras/focused { camera_id: _cameraId }
  }

  /**
   * Returns true if a camera has an active WebRTC stream with at least one video track.
   * Used by AnalyticsOverlay to decide whether to show the overlay.
   */
  public isLive(cameraId: string): boolean {
    const entry = this.entries.get(cameraId);
    return !!(entry?.stream?.active && entry.stream.getVideoTracks().length > 0);
  }

  private destroyEntry(cameraId: string) {
    const entry = this.entries.get(cameraId);
    if (!entry) return;

    if (entry.cleanupTimer) {
      clearTimeout(entry.cleanupTimer);
    }

    if (entry.pc) {
      try { entry.pc.close(); } catch (_) {}
    }

    if (entry.stream) {
      entry.stream.getTracks().forEach(t => {
        try { t.stop(); } catch (_) {}
      });
    }

    this.entries.delete(cameraId);
  }
}

export const webrtcStreamManager = new WebRTCStreamManager();
