import { useEffect, useState } from 'react'
import { Flame, CloudFog, Camera, Activity, AlertTriangle, Clock, PlayCircle, ShieldCheck, Video } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/utils'
import { api } from '@/api/api'
import { useCameraStateStore } from '@/store/useCameraStateStore'

export function FireAnalytics() {
  const [events, setEvents] = useState<any[]>([])
  const [coverage, setCoverage] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const states = useCameraStateStore(state => state.states)

  const parseTimestampMs = (ts: any): number => {
    if (!ts) return 0
    if (typeof ts === 'number') {
      return ts < 1e11 ? ts * 1000 : ts
    }
    const parsed = new Date(ts).getTime()
    return isNaN(parsed) ? 0 : parsed
  }

  const formatDateTimeStr = (ts: any) => {
    const ms = parseTimestampMs(ts)
    if (!ms) return { date: '—', time: '—', full: '—' }
    const d = new Date(ms)
    const day = d.getDate()
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec']
    const month = months[d.getMonth()]
    const year = d.getFullYear()
    const time = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
    return {
      date: `${day} ${month} ${year}`,
      time: time,
      full: `${day} ${month} ${year}, ${time}`
    }
  }


  const handleAcknowledge = async (eventId: string) => {
    if (!eventId) return
    try {
      await api.post(`/api/fire/events/${eventId}/acknowledge`, { note: 'Resolved by operator' })
      setEvents(prev => prev.map(evt => (evt.id === eventId || evt.event_id === eventId) ? { ...evt, acknowledged: true } : evt))
    } catch (err) {
      console.error("Failed to acknowledge event", err)
    }
  }

  const fetchEventsAndCoverage = async () => {
    try {
      const [eventsRes, covRes] = await Promise.all([
        api.get('/api/fire/events').catch(() => ({ data: { events: [] } })),
        api.get('/api/fire/coverage').catch(() => ({ data: null }))
      ])
      if (eventsRes.data?.events) {
        setEvents(eventsRes.data.events)
      }
      if (covRes.data) {
        setCoverage(covRes.data)
      }
    } catch (err) {
      console.error("Failed to fetch fire data", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchEventsAndCoverage()
    const interval = setInterval(fetchEventsAndCoverage, 5000)
    return () => clearInterval(interval)
  }, [])
  
  useEffect(() => {
    if (states) {
      let newFireEvents = false;
      Object.values(states || {}).forEach((state: any) => {
         const evts = state.events?.FireDetectionPlugin || state.events?.fire || [];
         if (evts.some((e: any) => e.event_type === 'FIRE_DETECTED' || e.event_type === 'SMOKE_DETECTED')) {
            newFireEvents = true;
         }
      });
      if (newFireEvents) {
        fetchEventsAndCoverage()
      }
    }
  }, [states]);

  if (loading) {
    return <div className="p-8 flex items-center justify-center h-full"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" /></div>
  }

  const nowMs = Date.now()
  const activeAlerts = events.filter(e => {
    const ms = parseTimestampMs(e.timestamp || e.started_at)
    return ms > 0 && (nowMs - ms) < 300000 && !e.acknowledged
  })
  const activeFire = activeAlerts.filter(e => e.kind === 'fire' || e.event_type === 'FIRE_DETECTED')
  const smokeAlerts = events.filter(e => e.kind === 'smoke' || e.event_type === 'SMOKE_DETECTED')
  const camerasMonitoring = coverage?.plugin_enabled_cameras ?? 0

  return (
    <div className="p-4 md:p-8 h-full overflow-y-auto">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-8 gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-red-500 to-orange-500 mb-2 tracking-tight flex items-center gap-3">
            <Flame className="w-8 h-8 text-red-500" />
            Fire & Smoke Security
          </h1>
          <p className="text-muted-foreground font-medium text-sm">
            AI-powered early fire and smoke detection across premises.
          </p>
        </div>
      </div>

      {/* Top Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat icon={Flame} label="Active Fire" value={activeFire.length} tone="bg-gradient-to-br from-red-800 to-pink-800/20 text-white border-red-800/30 shadow-[0_0_15px_rgba(239,68,68,0.4)]" />
        <Stat icon={CloudFog} label="Smoke Alerts" value={smokeAlerts.length} tone="bg-gradient-to-br from-orange-800 to-amber-800/20 text-white border-orange-800/30" />
        <Stat icon={Camera} label="Cameras Monitoring" value={camerasMonitoring} tone="bg-gradient-to-br from-blue-800 to-indigo-800/20 text-white border-blue-800/30" />
        <Stat icon={ShieldCheck} label="System Status" value={activeAlerts.length > 0 ? "Alerting" : "Healthy"} tone="bg-gradient-to-br from-emerald-800 to-teal-800/20 text-white border-emerald-800/30 shadow-[0_0_10px_rgba(16,185,129,0.3)]" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        
        {/* Live Events (Left Column) */}
        <div className="xl:col-span-1 space-y-4">
          <h2 className="text-lg font-bold text-blue-900 dark:text-white flex items-center gap-2">
            <Activity className="w-5 h-5 text-danger" /> Live Fire/Smoke Events
          </h2>
          
          <div className="glass border border-foreground/10 rounded-2xl overflow-hidden shadow-lg p-1">
            {activeAlerts.length > 0 ? (
              <div className="p-4 bg-gradient-to-r from-red-500/20 to-pink-500/20 flex flex-col gap-4">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-full bg-red-500/20 text-red-500 flex items-center justify-center animate-pulse">
                      <Flame className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="font-bold text-red-500 text-lg uppercase tracking-wider">Fire Detected!</h3>
                      <p className="text-xs text-red-500">{activeAlerts.length} Active alert(s) reported.</p>
                    </div>
                  </div>
                  <button 
                    onClick={() => {
                      activeAlerts.forEach(a => handleAcknowledge(a.id || a.event_id));
                    }}
                    className="w-full py-3 bg-gradient-to-r from-red-500 to-pink-500 text-white rounded-xl font-black shadow-lg shadow-red-500/20 hover:from-red-600 hover:to-pink-600 transition-colors"
                  >
                    Acknowledge All ({activeAlerts.length})
                  </button>
                </div>
            ) : (
              <div className="p-12 text-center flex flex-col items-center justify-center h-[300px] text-muted-foreground">
                <ShieldCheck className="w-16 h-16 mb-4 text-emerald-500/50" />
                <p className="font-medium text-blue-900 dark:text-white mb-1">No Active Threats</p>
                <p className="text-sm text-blue-700/80 dark:text-muted-foreground">All zones are currently clear of fire or smoke.</p>
              </div>
            )}
          </div>
        </div>

        {/* History (Right Column) */}
        <div className="xl:col-span-2 space-y-4">
          <h2 className="text-lg font-bold text-blue-900 dark:text-white flex items-center gap-2">
            <Clock className="w-5 h-5 text-blue-600 dark:text-muted-foreground" /> Detection History
          </h2>
          
          <div className="glass border border-foreground/10 rounded-2xl overflow-hidden shadow-lg">
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-[10px] tracking-wider uppercase text-blue-900 dark:text-gray-300 bg-blue-50/50 dark:bg-gray-800/20 font-black">
                    <tr>
                      <th className="px-6 py-4">Event</th>
                      <th className="px-6 py-4">Location</th>
                      <th className="px-6 py-4">Date & Time</th>
                      <th className="px-6 py-4">Confidence</th>
                      <th className="px-6 py-4">Media</th>
                      <th className="px-6 py-4">Status</th>
                    </tr>
                  </thead>
                <tbody className="divide-y divide-white/5">
                  {events.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center text-blue-800 dark:text-muted-foreground text-sm">
                        No fire or smoke incidents recorded.
                      </td>
                    </tr>
                  ) : (
                    events.map((item, i) => {
                      const isSmoke = item.kind === 'smoke' || item.event_type === 'SMOKE_DETECTED'
                      const eventLabel = isSmoke ? 'Smoke' : 'Fire'
                      const dt = formatDateTimeStr(item.timestamp || item.started_at)
                      const scoreVal = item.score ? Math.round(item.score * 100) : (item.confidence ? Math.round(item.confidence * 100) : 0)
                      const locationName = item.camera_name || item.camera_id || 'Camera'
                      const zoneName = item.zone_name || (item.zone_id ? `Zone ${item.zone_id}` : 'Full Frame')

                      return (
                        <tr key={item.id || item.event_id || i} className="hover:bg-foreground/5 transition-colors group">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <div className={cn("w-8 h-8 rounded-full flex items-center justify-center", !isSmoke ? 'bg-danger/20 text-danger' : 'bg-orange-500/20 text-orange-400')}>
                                {!isSmoke ? <Flame className="w-4 h-4" /> : <CloudFog className="w-4 h-4" />}
                              </div>
                              <div className="font-bold text-blue-900 dark:text-white">{eventLabel} Alert</div>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="font-medium text-blue-900 dark:text-white mb-1">{locationName}</div>
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-blue-100/60 dark:bg-foreground/10 text-blue-800 dark:text-muted-foreground">{zoneName}</span>
                          </td>
                          <td className="px-6 py-4">
                            <div className="font-medium text-blue-900 dark:text-blue-200 text-xs font-mono">{dt.full}</div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2">
                              <div className="w-16 h-1.5 bg-background/50 rounded-full overflow-hidden">
                                <div className={cn("h-full", scoreVal > 90 ? 'bg-danger' : 'bg-orange-400')} style={{ width: `${scoreVal}%` }}></div>
                              </div>
                              <span className="text-xs font-mono font-bold text-blue-900 dark:text-white">{scoreVal}%</span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2">
                              {item.snapshot_file ? (
                                <a href={item.snapshot_file} target="_blank" rel="noreferrer" className="w-8 h-8 rounded bg-background/50 border border-foreground/10 flex items-center justify-center cursor-pointer hover:border-primary transition-colors" title="View Snapshot">
                                  <Camera className="w-3.5 h-3.5 text-primary" />
                                </a>
                              ) : (
                                <div className="w-8 h-8 rounded bg-background/30 border border-foreground/5 flex items-center justify-center text-muted-foreground" title="No Snapshot">
                                  <Camera className="w-3.5 h-3.5 opacity-30" />
                                </div>
                              )}
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <button
                              disabled={item.acknowledged}
                              onClick={() => handleAcknowledge(item.id || item.event_id)}
                              className={cn(
                                "px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all cursor-pointer",
                                item.acknowledged ? 'bg-success/20 text-success cursor-default' : 'bg-warning/20 text-warning hover:bg-warning/40 hover:scale-105'
                              )}
                              title={item.acknowledged ? "Resolved by operator" : "Click to mark as Resolved"}
                            >
                              {item.acknowledged ? 'Resolved' : 'Active (Mark Resolved)'}
                            </button>
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}

function Stat({ icon: Icon, label, value, tone }: any) {
  return (
    <div className={cn("glass border rounded-2xl p-5 flex flex-col gap-4", tone)}>
      <div className="flex justify-between items-start">
        <div className={cn('p-2.5 rounded-xl bg-background/40 w-fit', tone)}>
          <Icon className="w-6 h-6" />
        </div>
        <div className="text-3xl font-black leading-none">{value}</div>
      </div>
      <div className="text-[11px] uppercase font-bold tracking-widest opacity-80 text-white">{label}</div>
    </div>
  )
}
