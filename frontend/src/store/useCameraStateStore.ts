import { create } from 'zustand'

interface CameraState {
  timestamp: number
  events: any
  detections?: any[]
  fps: number
  latency_ms: number
}

interface CameraStateStore {
  states: Record<string, CameraState>
  isConnected: boolean
  connect: () => void
  disconnect: () => void
  setCameraPlugins: (cameraId: string, allowedPlugins: string[]) => void
}

let ws: WebSocket | null = null;

export const useCameraStateStore = create<CameraStateStore>((set, get) => ({
  states: {},
  isConnected: false,
  setCameraPlugins: (cameraId: string, allowedPlugins: string[]) => {
    set((state) => {
      const camState = state.states[cameraId];
      if (!camState || !camState.events) return state;

      const filteredEvents: Record<string, any> = {};
      for (const [pName, pData] of Object.entries(camState.events)) {
        if (allowedPlugins.includes(pName)) {
          filteredEvents[pName] = pData;
        }
      }

      return {
        states: {
          ...state.states,
          [cameraId]: {
            ...camState,
            events: filteredEvents
          }
        }
      };
    });
  },
  connect: () => {
    if (ws) return;

    const token = localStorage.getItem('access_token') || '';
    // Don't even attempt a connection without a token — the backend will reject
    // it with 1008 (policy violation) and we'd spin in a reconnect loop.
    if (!token) return;

    console.log("Connecting to WebSocket...");
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/events?token=${encodeURIComponent(token)}`);

    ws.onopen = () => {
      console.log("WebSocket connected");
      set({ isConnected: true });
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "telemetry" && data.states) {
          set({ states: data.states });
        } else {
          // Fallback if the backend sends just the states directly
          set({ states: data });
        }
      } catch (e) {
        console.error("Failed to parse websocket message", e);
      }
    };

    ws.onclose = (event) => {
      console.log("WebSocket disconnected", event.code);
      set({ isConnected: false });
      ws = null;

      // Code 1008 = policy violation (invalid/missing token).
      // Do NOT reconnect — we'd just loop forever with the same bad token.
      // The App component will call connect() again once the user logs in.
      if (event.code === 1008) {
        console.warn("WebSocket closed due to invalid token. Waiting for re-authentication.");
        return;
      }

      // For normal disconnects (network blip, server restart), retry after 3s.
      setTimeout(() => get().connect(), 3000);
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };
  },
  disconnect: () => {
    if (ws) {
      ws.close();
      ws = null;
    }
  }
}))
