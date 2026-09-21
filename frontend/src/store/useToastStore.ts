import { create } from 'zustand'

export interface Toast {
  id: string
  title: string
  message: string
  type?: 'default' | 'success' | 'warning' | 'danger'
  cameraName?: string
}

export const playAlertSound = (type: 'danger' | 'warning' | 'success' = 'danger') => {
  try {
    const AudioContext = window.AudioContext || (window as any).webkitAudioContext
    if (!AudioContext) return
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()

    if (type === 'danger') {
      osc.type = 'sawtooth'
      osc.frequency.setValueAtTime(880, ctx.currentTime)
      osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.25)
      gain.gain.setValueAtTime(0.2, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25)
    } else if (type === 'warning') {
      osc.type = 'sine'
      osc.frequency.setValueAtTime(587.33, ctx.currentTime) // D5
      gain.gain.setValueAtTime(0.15, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.2)
    } else {
      osc.type = 'sine'
      osc.frequency.setValueAtTime(523.25, ctx.currentTime) // C5
      gain.gain.setValueAtTime(0.1, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15)
    }

    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.3)
  } catch (e) {
    // Ignored browser autoplay policy restrictions
  }
}

export const sendBrowserPushNotification = (title: string, body: string) => {
  try {
    if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted') {
      new Notification(title, {
        body,
        icon: '/favicon.ico',
        tag: 'devavision-alert',
      })
    }
  } catch (e) {
    // Gracefully ignore notification errors
  }
}

interface ToastStore {
  toasts: Toast[]
  soundEnabled: boolean
  pushEnabled: boolean
  setSoundEnabled: (enabled: boolean) => void
  setPushEnabled: (enabled: boolean) => Promise<boolean>
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void
}

export const useToastStore = create<ToastStore>((set, get) => ({
  toasts: [],
  soundEnabled: localStorage.getItem('alert_sound_enabled') !== 'false',
  pushEnabled: localStorage.getItem('alert_push_enabled') !== 'false',
  setSoundEnabled: (enabled) => {
    localStorage.setItem('alert_sound_enabled', enabled ? 'true' : 'false')
    set({ soundEnabled: enabled })
  },
  setPushEnabled: async (enabled) => {
    if (enabled && typeof window !== 'undefined' && 'Notification' in window) {
      if (Notification.permission !== 'granted') {
        const perm = await Notification.requestPermission()
        if (perm !== 'granted') {
          set({ pushEnabled: false })
          localStorage.setItem('alert_push_enabled', 'false')
          return false
        }
      }
    }
    localStorage.setItem('alert_push_enabled', enabled ? 'true' : 'false')
    set({ pushEnabled: enabled })
    return enabled
  },
  addToast: (toast) => {
    const id = Math.random().toString(36).substring(2, 9)
    set((state) => ({ toasts: [...state.toasts, { ...toast, id }] }))

    // Play synthesized alert sound if sound enabled & danger/warning
    if (get().soundEnabled && (toast.type === 'danger' || toast.type === 'warning')) {
      playAlertSound(toast.type)
    }

    // Trigger browser push notification if enabled & danger/warning
    if (get().pushEnabled && (toast.type === 'danger' || toast.type === 'warning')) {
      sendBrowserPushNotification(
        `${toast.type === 'danger' ? '🚨 CRITICAL ALERT' : '⚠️ WARNING'}: ${toast.title}`,
        toast.cameraName ? `[${toast.cameraName}] ${toast.message}` : toast.message
      )
    }

    // Auto remove after 4 seconds
    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }))
    }, 4000)
  },
  removeToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}))
