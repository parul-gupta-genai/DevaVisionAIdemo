import { X, Activity, ShieldAlert, Clock, Fingerprint, Car, Loader2, AlertTriangle, Flame, Users, Eye, ShieldCheck, Truck } from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import { useCameraStateStore } from '@/store/useCameraStateStore'
import { cn } from '@/utils/utils'
import { useState, useEffect } from 'react'
import { api } from '@/api/api'

const TABS = [
  { id: 'alerts', icon: ShieldAlert, label: 'Alerts' },
  { id: 'ai', icon: Fingerprint, label: 'AI Detection' },
  { id: 'health', icon: Activity, label: 'Health' },
  { id: 'events', icon: Clock, label: 'Events' },
]

/** Severity badge color map */
const SEVERITY_STYLES: Record<string, string> = {
  danger: 'border-danger bg-danger/10 text-danger',
  warning: 'border-warning bg-warning/10 text-warning',
  info: 'border-primary bg-primary/10 text-primary',
}

/** Plugin name → human-friendly icon */
function pluginIcon(pluginName: string) {
  if (pluginName.includes('Fire')) return Flame
  if (pluginName.includes('Fight') || pluginName.includes('Intrusion')) return AlertTriangle
  if (pluginName.includes('People') || pluginName.includes('Visitor')) return Users
  if (pluginName.includes('ANPR') || pluginName.includes('Vehicle')) return Car
  if (pluginName.includes('PPE') || pluginName.includes('Safety')) return ShieldCheck
  if (pluginName.includes('Material')) return Truck
  return Eye
}

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function RightPanel() {
  const { rightPanelOpen, toggleRightPanel } = useAppStore()
  const states = useCameraStateStore(state => state.states)
  const [activeTab, setActiveTab] = useState('alerts')

  // -- Alerts & Events from /events API --
  const [events, setEvents] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  // -- Health from /telemetry API --
  const [tele, setTele] = useState<any>(null)

  // Fetch events when panel opens or tab switches to alerts/events
  useEffect(() => {
    if (!rightPanelOpen) return
    if (activeTab !== 'alerts' && activeTab !== 'events') return

    setLoading(true)
    api.get('/events')
      .then(res => {
        if (res.data && Array.isArray(res.data)) {
          setEvents(res.data)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [rightPanelOpen, activeTab])

  // Re-fetch events when WebSocket pushes new camera states (debounced by tab)
  useEffect(() => {
    if (!rightPanelOpen) return
    if (activeTab !== 'alerts' && activeTab !== 'events') return

    // Light refresh — no loading spinner for live updates
    api.get('/events')
      .then(res => {
        if (res.data && Array.isArray(res.data)) {
          setEvents(res.data)
        }
      })
      .catch(() => {})
  }, [states])

  // Fetch telemetry for health tab
  useEffect(() => {
    if (!rightPanelOpen || activeTab !== 'health') return

    const fetchTele = () => {
      api.get('/telemetry')
        .then(res => setTele(res.data))
        .catch(() => {})
    }
    fetchTele()
    const timer = setInterval(fetchTele, 3000)
    return () => clearInterval(timer)
  }, [rightPanelOpen, activeTab])

  // Derived data
  const alertEvents = events.filter(
    (e: any) => e.event_type === 'danger' || e.event_type === 'warning'
  ).slice(0, 20)

  const recentEvents = events.slice(0, 30)

  // Live AI detections from WebSocket
  const liveDetections: { camera: string; pluginName: string; summary: string; data: any }[] = []
  Object.entries(states || {}).forEach(([camId, camState]: [string, any]) => {
    const camEvents = camState?.events || {}
    Object.entries(camEvents).forEach(([pluginName, pluginData]: [string, any]) => {
      if (!pluginData || pluginName === 'timestamp') return
      const items = Array.isArray(pluginData) ? pluginData : [pluginData]
      items.forEach((item: any) => {
        let summary = ''
        if (item.description) summary = item.description
        else if (item.gesture) summary = `Gesture: ${item.gesture}`
        else if (item.plate_text) summary = `Plate: ${item.plate_text}`
        else if (item.name) summary = item.name
        else if (item.person_count != null) summary = `${item.person_count} people`
        else if (item.count != null) summary = `Count: ${item.count}`
        else summary = pluginName.replace('Plugin', '')

        liveDetections.push({ camera: camId, pluginName, summary, data: item })
      })
    })
  })

  return (
    <aside 
      className={cn(
        "bg-card border-l border-border transition-all duration-300 ease-in-out shrink-0 flex flex-col z-40 fixed right-0 top-16 bottom-0 shadow-2xl",
        rightPanelOpen ? "w-80 translate-x-0" : "w-80 translate-x-full"
      )}
    >
      <div className="flex items-center justify-between p-4 border-b border-border bg-background/50">
        <h2 className="font-semibold text-lg tracking-wide">Live Intel</h2>
        <button onClick={toggleRightPanel} className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="flex p-2 gap-1 border-b border-border bg-background/30">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex-1 flex flex-col items-center gap-1.5 p-2 rounded-md transition-all text-xs font-medium",
              activeTab === tab.id ? "bg-primary text-primary-foreground shadow-md" : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">

        {/* Loading state */}
        {loading && (activeTab === 'alerts' || activeTab === 'events') && (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            <span className="text-sm">Loading...</span>
          </div>
        )}

        {/* ===== ALERTS TAB ===== */}
        {activeTab === 'alerts' && !loading && (
          <>
            {alertEvents.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <ShieldAlert className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm">No active alerts</p>
                <p className="text-xs mt-1">System is running smoothly</p>
              </div>
            ) : (
              alertEvents.map((ev: any, i: number) => {
                const severity = ev.event_type || 'info'
                const styles = SEVERITY_STYLES[severity] || SEVERITY_STYLES.info
                return (
                  <div key={ev.id || i} className={cn("p-3 rounded-lg border-l-4 flex flex-col gap-1 cursor-pointer hover:opacity-80 transition-opacity", styles)}>
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span className="font-semibold">
                        {severity === 'danger' ? '🔴 Critical' : '🟡 Warning'}
                      </span>
                      <span>{ev.timestamp ? timeAgo(ev.timestamp) : ''}</span>
                    </div>
                    <p className="text-sm font-medium text-foreground">{ev.description || 'Alert'}</p>
                    <p className="text-xs text-muted-foreground">
                      {ev.camera_id || 'Unknown Camera'}
                      {ev.snapshot && ' • 📸 Snapshot'}
                    </p>
                  </div>
                )
              })
            )}
          </>
        )}

        {/* ===== AI DETECTION TAB (Live from WebSocket) ===== */}
        {activeTab === 'ai' && (
          <>
            {liveDetections.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Fingerprint className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm">No live detections</p>
                <p className="text-xs mt-1">AI models are idle or no cameras active</p>
              </div>
            ) : (
              liveDetections.slice(0, 25).map((det, i) => {
                const IconComp = pluginIcon(det.pluginName)
                return (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-muted/30 hover:bg-muted/50 cursor-pointer transition-colors border border-border">
                    <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center shrink-0">
                      <IconComp className="w-5 h-5 text-primary" />
                    </div>
                    <div className="flex flex-col flex-1 overflow-hidden">
                      <span className="text-sm font-medium truncate">{det.summary}</span>
                      <span className="text-xs text-muted-foreground truncate">
                        {det.pluginName.replace('Plugin', '')} • {det.camera}
                      </span>
                    </div>
                    <div className="w-2 h-2 rounded-full bg-success animate-pulse shrink-0" title="Live" />
                  </div>
                )
              })
            )}
          </>
        )}

        {/* ===== HEALTH TAB ===== */}
        {activeTab === 'health' && (
          <>
            {!tele ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                <span className="text-sm">Loading telemetry...</span>
              </div>
            ) : (
              <>
                <HealthBar label="CPU Usage" value={tele.cpu_usage} color="bg-blue-500" />
                <HealthBar label="RAM Usage" value={tele.ram_usage} color="bg-purple-500" />
                <HealthBar label="GPU Usage" value={tele.gpu_usage} color="bg-green-500" />
                {tele.disk_usage != null && (
                  <HealthBar label="Disk Usage" value={tele.disk_usage} color="bg-orange-500" />
                )}
                {tele.cpu_temp != null && (
                  <div className="p-3 rounded-lg bg-muted/30 border border-border">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">CPU Temp</span>
                      <span className={cn("font-bold", tele.cpu_temp > 80 ? "text-danger" : "text-foreground")}>
                        {Math.round(tele.cpu_temp)}°C
                      </span>
                    </div>
                  </div>
                )}
                {tele.gpu_temp != null && (
                  <div className="p-3 rounded-lg bg-muted/30 border border-border">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">GPU Temp</span>
                      <span className={cn("font-bold", tele.gpu_temp > 85 ? "text-danger" : "text-foreground")}>
                        {Math.round(tele.gpu_temp)}°C
                      </span>
                    </div>
                  </div>
                )}
                <div className="p-3 rounded-lg bg-muted/30 border border-border">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Active Cameras</span>
                    <span className="font-bold text-foreground">
                      {Object.keys(states || {}).length}
                    </span>
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {/* ===== EVENTS TAB ===== */}
        {activeTab === 'events' && !loading && (
          <>
            {recentEvents.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Clock className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm">No recent events</p>
              </div>
            ) : (
              recentEvents.map((ev: any, i: number) => {
                const severity = ev.event_type || 'info'
                const dotColor = severity === 'danger' ? 'bg-danger' : severity === 'warning' ? 'bg-warning' : 'bg-primary'
                return (
                  <div key={ev.id || i} className="flex items-start gap-3 p-3 rounded-lg bg-muted/30 hover:bg-muted/50 cursor-pointer transition-colors border border-border">
                    <div className={cn("w-2.5 h-2.5 rounded-full mt-1.5 shrink-0", dotColor)} />
                    <div className="flex flex-col flex-1 overflow-hidden">
                      <span className="text-sm font-medium truncate">{ev.description || 'Event'}</span>
                      <span className="text-xs text-muted-foreground truncate">
                        {ev.camera_id || 'System'} • {ev.timestamp ? timeAgo(ev.timestamp) : ''}
                      </span>
                    </div>
                  </div>
                )
              })
            )}
          </>
        )}

      </div>
    </aside>
  )
}

/** Reusable progress bar for health metrics */
function HealthBar({ label, value, color }: { label: string; value: number | null; color: string }) {
  const pct = value != null ? Math.round(value) : 0
  const isHigh = pct > 85
  return (
    <div className="p-3 rounded-lg bg-muted/30 border border-border">
      <div className="flex justify-between text-sm mb-2">
        <span className="text-muted-foreground">{label}</span>
        <span className={cn("font-bold", isHigh ? "text-danger" : "text-foreground")}>{pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500", isHigh ? "bg-danger" : color)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
