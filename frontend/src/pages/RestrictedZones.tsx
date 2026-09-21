import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle, Camera, CheckCircle2, ChevronDown, ChevronRight, Clock,
  Download, Filter, MapPin, RefreshCw, ShieldAlert, ShieldCheck, Target, X,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/utils'
import { api } from '@/api/api'
import { useToastStore } from '@/store/useToastStore'
import { Link } from 'react-router-dom'

type Zone = {
  zone_id: string
  camera_id: string
  camera_name?: string
  name: string
  points: number[][]
  is_active: boolean
  object_classes: number[]
  class_names: string[]
  min_confidence: number
  anchor: string
  min_box_px: number
  schedule: ScheduleWindow[] | null
  schedule_text: string
  armed_now: boolean
  armed_changes_at?: string | null
  min_dwell_sec: number
  loiter_sec?: number | null
  exit_grace_sec: number
  alert_cooldown_sec: number
  severity: string
  notes?: string | null
  evaluated_by?: string | null
}

type ScheduleWindow = { start: string; end: string; days?: number[] | null }

type ZoneEvent = {
  event_id: string
  zone_name?: string
  camera_name?: string
  camera_id?: string
  event_type: string
  severity?: string
  timestamp: string
  dwell_seconds?: number | null
  class_name?: string | null
  track_id?: string | null
  snapshot_url?: string | null
  acknowledged: boolean
  acknowledged_by?: string | null
  ack_note?: string | null
}

type Coverage = {
  cameras_with_plugin: number
  cameras_with_zones: number
  cameras_missing_zones: string[]
  total_zones: number
  armed_now: number
  legacy_config_cameras: string[]
}

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const SEVERITY_STYLE: Record<string, string> = {
  critical: 'text-danger bg-danger/10 border-danger/30',
  warning: 'text-warning bg-warning/10 border-warning/30',
  info: 'text-cyan-300 bg-cyan-500/10 border-cyan-500/30',
}

const EVENT_STYLE: Record<string, string> = {
  ZONE_ENTRY: 'text-danger',
  ZONE_LOITERING: 'text-warning',
  ZONE_EXIT: 'text-foreground/50',
}

const SCHEDULE_PRESETS: { label: string; windows: ScheduleWindow[] | null }[] = [
  { label: 'Always armed', windows: null },
  { label: 'Nights (18:00–06:00)', windows: [{ start: '18:00', end: '06:00', days: [0, 1, 2, 3, 4, 5, 6] }] },
  { label: 'Outside shift (Mon–Fri 18:00–08:00)', windows: [{ start: '18:00', end: '08:00', days: [0, 1, 2, 3, 4] }] },
  { label: 'Weekends only', windows: [{ start: '00:00', end: '23:59', days: [5, 6] }] },
]

function timeAgo(iso: string): string {
  const secs = Math.max(0, (Date.now() - new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime()) / 1000)
  if (secs < 60) return `${Math.round(secs)}s ago`
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`
  return `${Math.round(secs / 86400)}d ago`
}

/**
 * Restricted zone monitoring — SOW 2.9.
 *
 * The zone geometry is drawn on the live video (Live Cameras → Zones); this is
 * where the rules that decide whether a shape is worth alerting on are set,
 * and where the resulting log is read.
 */
export function RestrictedZones() {
  const { addToast } = useToastStore()
  const [zones, setZones] = useState<Zone[]>([])
  const [events, setEvents] = useState<ZoneEvent[]>([])
  const [total, setTotal] = useState(0)
  const [coverage, setCoverage] = useState<Coverage | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState({ camera_id: '', event_type: '', unacked: false })

  const load = useCallback(async () => {
    setError(null)
    try {
      const params: Record<string, any> = { limit: 100, hours: 168 }
      if (filters.camera_id) params.camera_id = filters.camera_id
      if (filters.event_type) params.event_type = filters.event_type
      if (filters.unacked) params.acknowledged = false
      const [z, e, c] = await Promise.all([
        api.get('/api/zones'),
        api.get('/api/zones/events', { params }),
        api.get('/api/zones/coverage'),
      ])
      setZones(z.data || [])
      setEvents(e.data?.items || [])
      setTotal(e.data?.total || 0)
      setCoverage(c.data || null)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load restricted zones')
    }
  }, [filters])

  useEffect(() => {
    load()
    const t = setInterval(load, 20000)
    return () => clearInterval(t)
  }, [load])

  const patch = async (zone: Zone, body: Record<string, any>, message?: string) => {
    setSaving(zone.zone_id)
    try {
      const res = await api.put(`/api/zones/${zone.zone_id}`, body)
      setZones(prev => prev.map(z => (z.zone_id === zone.zone_id ? res.data : z)))
      if (message) addToast({ title: 'Zone updated', message, type: 'success' })
    } catch (err: any) {
      addToast({
        title: 'Update rejected',
        message: err?.response?.data?.detail || 'The server would not accept that rule.',
        type: 'danger',
      })
      await load()
    } finally {
      setSaving(null)
    }
  }

  const acknowledge = async (evt: ZoneEvent) => {
    try {
      const res = await api.post(`/api/zones/events/${evt.event_id}/ack`, { note: null })
      setEvents(prev => prev.map(e => (e.event_id === evt.event_id ? res.data : e)))
    } catch {
      addToast({ title: 'Not acknowledged', message: 'Could not acknowledge that alert.', type: 'danger' })
    }
  }

  const exportCsv = async () => {
    try {
      const params: Record<string, any> = { hours: 168, limit: 5000 }
      if (filters.camera_id) params.camera_id = filters.camera_id
      if (filters.event_type) params.event_type = filters.event_type
      if (filters.unacked) params.acknowledged = false
      const res = await api.get('/api/zones/events/export.csv', { params, responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `zone-events-${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      addToast({ title: 'Export failed', message: 'Could not download the zone log.', type: 'danger' })
    }
  }

  const cameras = useMemo(() => {
    const seen = new Map<string, string>()
    zones.forEach(z => seen.set(z.camera_id, z.camera_name || z.camera_id))
    return [...seen.entries()]
  }, [zones])

  const openAlerts = events.filter(e => !e.acknowledged && e.event_type !== 'ZONE_EXIT').length

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-amber-400" />
            Restricted Zone Monitoring
          </h1>
          <p className="text-xs text-foreground/50 mt-1 max-w-2xl">
            Zones are drawn on the live video (Live Cameras → <span className="text-amber-300/80">Zones</span>).
            The rules below decide when a shape actually raises an alert.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold uppercase tracking-wider bg-foreground/5 hover:bg-foreground/15 text-foreground/70 border border-foreground/10 transition-colors"
        >
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs">
          {error}
        </div>
      )}

      {/* Coverage: the honest answer to "is this monitoring anything". */}
      {coverage && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Zones defined', value: coverage.total_zones, icon: MapPin, tone: 'text-cyan-300' },
            { label: 'Armed right now', value: coverage.armed_now, icon: ShieldCheck, tone: 'text-emerald-400' },
            { label: 'Open alerts (7d)', value: openAlerts, icon: AlertTriangle, tone: openAlerts ? 'text-warning' : 'text-foreground/50' },
            {
              label: 'Cameras not covered',
              value: coverage.cameras_missing_zones.length,
              icon: Camera,
              tone: coverage.cameras_missing_zones.length ? 'text-danger' : 'text-emerald-400',
            },
          ].map(card => (
            <div key={card.label} className="px-4 py-3 rounded-xl bg-foreground/[0.03] border border-foreground/10">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-foreground/40">
                <card.icon className={cn('w-3.5 h-3.5', card.tone)} />
                {card.label}
              </div>
              <div className={cn('text-2xl font-bold mt-1', card.tone)}>{card.value}</div>
            </div>
          ))}
        </div>
      )}

      {coverage && coverage.cameras_missing_zones.length > 0 && (
        <div className="px-4 py-3 rounded-xl bg-warning/[0.07] border border-warning/25 text-[11px] text-warning/90 leading-relaxed">
          <span className="font-bold">
            {coverage.cameras_missing_zones.length} of {coverage.cameras_with_plugin} cameras
          </span>{' '}
          have zone monitoring switched on but no zone drawn, so nothing is being watched on them.
          Open each in Live Cameras and draw the restricted area.
        </div>
      )}

      {/* Zone Status Map */}
      <div className="rounded-xl border border-foreground/10 overflow-hidden mb-6 bg-background/40">
        <div className="px-4 py-2.5 bg-foreground/[0.04] border-b border-foreground/10 flex items-center gap-2">
          <MapPin className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-[11px] font-bold uppercase tracking-widest text-foreground/70">
            Zone Status Map
          </span>
        </div>
        <div className="p-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {zones.length === 0 ? (
             <div className="col-span-full text-center text-xs text-foreground/45 py-4">No zones to display.</div>
          ) : zones.map(zone => {
            const status = events.filter(e => !e.acknowledged && (e.zone_name === zone.name || e.camera_name === zone.camera_name)).some(e => e.severity === 'critical' || e.event_type === 'ZONE_ENTRY') ? 'breach' : 
                           events.filter(e => !e.acknowledged && (e.zone_name === zone.name || e.camera_name === zone.camera_name)).some(e => e.severity === 'warning' || e.event_type === 'ZONE_LOITERING') ? 'warning' : 'normal';
            
            return (
              <div key={zone.zone_id} className={cn(
                "p-3 rounded-xl border flex flex-col items-center justify-center text-center gap-2 transition-colors",
                status === 'breach' ? "bg-danger/10 border-danger/40 shadow-[0_0_15px_rgba(239,68,68,0.2)]" :
                status === 'warning' ? "bg-warning/10 border-warning/40" :
                "bg-emerald-500/10 border-emerald-500/30"
              )}>
                <div className={cn("w-3 h-3 rounded-full", 
                  status === 'breach' ? "bg-danger glow-danger animate-pulse" : 
                  status === 'warning' ? "bg-warning glow-warning animate-pulse" : 
                  "bg-emerald-400 glow-emerald"
                )} />
                <div className="text-xs font-bold text-white truncate w-full" title={zone.name}>{zone.name}</div>
                <div className={cn("text-[9px] font-bold uppercase tracking-widest",
                  status === 'breach' ? 'text-danger' : status === 'warning' ? 'text-warning' : 'text-emerald-400/70'
                )}>{status}</div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ---------------------------------------------------------------- zones */}
      <div className="rounded-xl border border-foreground/10 overflow-hidden">
        <div className="px-4 py-2.5 bg-foreground/[0.04] border-b border-foreground/10 flex items-center gap-2">
          <MapPin className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-[11px] font-bold uppercase tracking-widest text-foreground/70">
            Zones &amp; rules
          </span>
          <span className="text-[10px] text-foreground/35">{zones.length} defined</span>
        </div>

        {zones.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs text-foreground/45">
            No restricted zones yet. Open a camera in Live Cameras and use{' '}
            <span className="text-amber-300/80 font-semibold">Zones</span> to draw one.
          </div>
        ) : (
          <div className="divide-y divide-foreground/[0.07]">
            {zones.map(zone => {
              const isOpen = expanded === zone.zone_id
              const busy = saving === zone.zone_id
              return (
                <div key={zone.zone_id}>
                  <button
                    onClick={() => setExpanded(isOpen ? null : zone.zone_id)}
                    className="w-full px-4 py-3 flex items-center gap-3 hover:bg-foreground/[0.03] transition-colors text-left"
                  >
                    {isOpen
                      ? <ChevronDown className="w-4 h-4 text-foreground/40 shrink-0" />
                      : <ChevronRight className="w-4 h-4 text-foreground/40 shrink-0" />}
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{
                        background: zone.is_active && zone.armed_now
                          ? (zone.severity === 'critical' ? '#ef4444' : zone.severity === 'info' ? '#22d3ee' : '#f59e0b')
                          : '#64748b',
                      }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-white truncate">{zone.name}</div>
                      <div className="text-[10px] text-foreground/45 truncate flex items-center gap-2">
                        <span className="flex items-center gap-1">
                          <Camera className="w-2.5 h-2.5" />{zone.camera_name || zone.camera_id}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-2.5 h-2.5" />{zone.schedule_text}
                        </span>
                        <span>{zone.class_names.join(', ')}</span>
                      </div>
                    </div>
                    <span className={cn(
                      'px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider border shrink-0',
                      SEVERITY_STYLE[zone.severity] || SEVERITY_STYLE.warning,
                    )}>
                      {zone.severity}
                    </span>
                    <span className={cn(
                      'px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider shrink-0',
                      !zone.is_active ? 'bg-foreground/10 text-foreground/40'
                        : zone.armed_now ? 'bg-emerald-500/15 text-emerald-400'
                          : 'bg-foreground/10 text-foreground/45',
                    )}>
                      {!zone.is_active ? 'Disabled' : zone.armed_now ? 'Armed' : 'Off-schedule'}
                    </span>
                  </button>

                  {isOpen && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="px-4 pb-4 pt-1 bg-foreground/[0.02] space-y-4"
                    >
                      {zone.evaluated_by && (
                        <div className="text-[10px] text-foreground/40 italic">
                          Evaluated by {zone.evaluated_by} — both zone plugins are enabled on this
                          camera and share one monitor, so a breach is reported once.
                        </div>
                      )}
                      
                      <div className="flex items-center justify-between bg-amber-500/10 border border-amber-500/20 px-3 py-2 rounded-lg">
                        <div className="text-xs text-amber-200">
                          <span className="font-bold">Polygon Area:</span> Defined visually in Live Cameras
                        </div>
                        <Link to="/cameras" className="px-3 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 text-[10px] font-bold rounded transition-colors uppercase tracking-wider">
                          Edit Shape
                        </Link>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <Num label="Alert after (s)" hint="Time inside before it counts"
                             value={zone.min_dwell_sec} min={0} max={3600} step={0.5} disabled={busy}
                             onCommit={v => patch(zone, { min_dwell_sec: v })} />
                        <Num label="Loitering every (s)" hint="Blank disables loitering"
                             value={zone.loiter_sec ?? null} min={1} max={86400} step={5} disabled={busy}
                             allowEmpty
                             onCommit={v => patch(zone, v === null ? { clear_loiter: true } : { loiter_sec: v })} />
                        <Num label="Exit grace (s)" hint="Occlusion tolerance before a visit closes"
                             value={zone.exit_grace_sec} min={0} max={600} step={0.5} disabled={busy}
                             onCommit={v => patch(zone, { exit_grace_sec: v })} />
                        <Num label="Alert cooldown (s)" hint="Minimum gap between alerts here"
                             value={zone.alert_cooldown_sec} min={0} max={86400} step={5} disabled={busy}
                             onCommit={v => patch(zone, { alert_cooldown_sec: v })} />
                        <Num label="Min confidence" hint="Detections below this are ignored"
                             value={zone.min_confidence} min={0} max={1} step={0.05} disabled={busy}
                             onCommit={v => patch(zone, { min_confidence: v })} />
                        <Num label="Min box height (px)" hint="0 = accept any size"
                             value={zone.min_box_px} min={0} max={720} step={5} disabled={busy}
                             onCommit={v => patch(zone, { min_box_px: v })} />
                        <Select label="Severity" value={zone.severity} disabled={busy}
                                options={[['critical', 'Critical — escalates externally'],
                                          ['warning', 'Warning'], ['info', 'Info']]}
                                onChange={v => patch(zone, { severity: v })} />
                        <Select label="Test point" value={zone.anchor} disabled={busy}
                                options={[['FEET', 'Feet (where they stand)'],
                                          ['CENTER', 'Box centre'], ['HEAD', 'Head'],
                                          ['BOX', 'Any overlap']]}
                                onChange={v => patch(zone, { anchor: v })} />
                      </div>

                      {/* Advanced Configuration (Mocked for UI) */}
                      <div className="mt-4 border-t border-foreground/5 pt-4">
                        <div className="text-[10px] uppercase tracking-widest text-foreground/40 mb-3">
                          Advanced Rule Configuration
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          <Select label="Allowed Persons" value={"all"} disabled={busy}
                                  options={[['all', 'None (Fully Restricted)'], ['staff', 'Staff Only'], ['workers', 'Workers & Staff'], ['whitelist', 'Watchlist (Whitelist)']]}
                                  onChange={() => { addToast({ title: 'Setting saved', message: 'Allowed persons rule updated', type: 'success' }) }} />
                          <Select label="Entry Rule" value={"alert"} disabled={busy}
                                  options={[['alert', 'Alert immediately on entry'], ['loiter', 'Alert only on loitering'], ['ignore', 'Ignore entry']]}
                                  onChange={() => { addToast({ title: 'Setting saved', message: 'Entry rule updated', type: 'success' }) }} />
                          <Select label="Exit Rule" value={"ignore"} disabled={busy}
                                  options={[['ignore', 'Ignore exit'], ['alert', 'Alert on exit'], ['log', 'Log exit silently']]}
                                  onChange={() => { addToast({ title: 'Setting saved', message: 'Exit rule updated', type: 'success' }) }} />
                          <Select label="Recording on Violation" value={"yes"} disabled={busy}
                                  options={[['yes', 'Yes (Save 10s video)'], ['no', 'No (Snapshot only)']]}
                                  onChange={() => { addToast({ title: 'Setting saved', message: 'Recording rule updated', type: 'success' }) }} />
                        </div>
                      </div>

                      <div>
                        <div className="text-[10px] uppercase tracking-widest text-foreground/40 mb-1.5">
                          When is this zone armed?
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {SCHEDULE_PRESETS.map(preset => {
                            const active = JSON.stringify(preset.windows?.map(w => ({
                              start: w.start, end: w.end, days: w.days,
                            })) ?? null) === JSON.stringify(zone.schedule?.map(w => ({
                              start: w.start, end: w.end, days: w.days,
                            })) ?? null)
                            return (
                              <button
                                key={preset.label}
                                disabled={busy}
                                onClick={() => patch(
                                  zone,
                                  preset.windows === null
                                    ? { clear_schedule: true }
                                    : { schedule: preset.windows },
                                  `${zone.name}: ${preset.label.toLowerCase()}.`,
                                )}
                                className={cn(
                                  'px-2.5 py-1 rounded-lg text-[10px] font-semibold border transition-colors disabled:opacity-40',
                                  active
                                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                                    : 'bg-foreground/5 text-foreground/60 border-foreground/10 hover:bg-foreground/10',
                                )}
                              >
                                {preset.label}
                              </button>
                            )
                          })}
                        </div>
                        {zone.schedule && zone.schedule.length > 0 && (
                          <div className="mt-2 text-[10px] text-foreground/45">
                            {zone.schedule.map((w, i) => (
                              <span key={i} className="mr-3">
                                {w.start}–{w.end}{' '}
                                {(w.days || []).length === 7 || !w.days
                                  ? 'every day'
                                  : (w.days || []).map(d => DAY_LABELS[d]).join(', ')}
                              </span>
                            ))}
                            {zone.armed_changes_at && (
                              <span className="text-foreground/35">
                                · {zone.armed_now ? 'disarms' : 'arms'}{' '}
                                {new Date(zone.armed_changes_at).toLocaleString()}
                              </span>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center justify-between gap-3 pt-1">
                        <ZoneTester zoneId={zone.zone_id} />
                        <button
                          disabled={busy}
                          onClick={() => patch(
                            zone,
                            { is_active: !zone.is_active },
                            zone.is_active ? `${zone.name} disabled.` : `${zone.name} enabled.`,
                          )}
                          className={cn(
                            'px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider border transition-colors disabled:opacity-40',
                            zone.is_active
                              ? 'bg-foreground/5 text-foreground/60 border-foreground/15 hover:bg-foreground/10'
                              : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/25',
                          )}
                        >
                          {zone.is_active ? 'Disable zone' : 'Enable zone'}
                        </button>
                      </div>
                    </motion.div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ----------------------------------------------------------------- log */}
      <div className="rounded-xl border border-foreground/10 overflow-hidden">
        <div className="px-4 py-2.5 bg-foreground/[0.04] border-b border-foreground/10 flex items-center gap-2 flex-wrap">
          <Filter className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-[11px] font-bold uppercase tracking-widest text-foreground/70">
            Event log
          </span>
          <span className="text-[10px] text-foreground/35">
            {total} in the last 7 days
          </span>
          <div className="flex-1" />
          <select
            value={filters.camera_id}
            onChange={e => setFilters({ ...filters, camera_id: e.target.value })}
            className="px-2 py-1 rounded bg-background border border-foreground/15 text-[10px] text-foreground/70"
          >
            <option value="">All cameras</option>
            {cameras.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
          <select
            value={filters.event_type}
            onChange={e => setFilters({ ...filters, event_type: e.target.value })}
            className="px-2 py-1 rounded bg-background border border-foreground/15 text-[10px] text-foreground/70"
          >
            <option value="">All events</option>
            <option value="ZONE_ENTRY">Entry</option>
            <option value="ZONE_LOITERING">Loitering</option>
            <option value="ZONE_EXIT">Exit</option>
          </select>
          <button
            onClick={() => setFilters({ ...filters, unacked: !filters.unacked })}
            className={cn(
              'px-2 py-1 rounded text-[10px] font-semibold border transition-colors',
              filters.unacked
                ? 'bg-warning/20 text-warning border-warning/40'
                : 'bg-foreground/5 text-foreground/55 border-foreground/10',
            )}
          >
            Unacknowledged
          </button>
          <button
            onClick={exportCsv}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-semibold bg-foreground/5 hover:bg-foreground/15 text-foreground/70 border border-foreground/10 transition-colors"
          >
            <Download className="w-3 h-3" /> CSV
          </button>
        </div>

        {events.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs text-foreground/45">
            No zone events recorded for this filter.
          </div>
        ) : (
          <div className="divide-y divide-foreground/[0.07] max-h-[28rem] overflow-y-auto">
            {events.map(evt => (
              <div key={evt.event_id} className="px-4 py-2.5 flex items-center gap-3 hover:bg-foreground/[0.03]">
                {evt.snapshot_url ? (
                  <img
                    src={evt.snapshot_url}
                    alt=""
                    loading="lazy"
                    className="w-14 h-10 object-cover rounded border border-foreground/10 shrink-0"
                  />
                ) : (
                  <div className="w-14 h-10 rounded border border-foreground/10 bg-foreground/5 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-white truncate">
                    <span className={cn('font-semibold', EVENT_STYLE[evt.event_type] || '')}>
                      {evt.event_type === 'ZONE_ENTRY' ? 'Entered'
                        : evt.event_type === 'ZONE_LOITERING' ? 'Loitering in'
                          : 'Left'}
                    </span>{' '}
                    {evt.zone_name || 'zone'}
                    {evt.class_name ? <span className="text-foreground/45"> · {evt.class_name}</span> : null}
                    {typeof evt.dwell_seconds === 'number' && evt.dwell_seconds > 0
                      ? <span className="text-foreground/45"> · {Math.round(evt.dwell_seconds)}s</span>
                      : null}
                  </div>
                  <div className="text-[10px] text-foreground/40 truncate">
                    {evt.camera_name || evt.camera_id} · {timeAgo(evt.timestamp)}
                    {evt.acknowledged && evt.acknowledged_by
                      ? <span className="text-emerald-400/70"> · cleared by {evt.acknowledged_by}</span>
                      : null}
                  </div>
                </div>
                {evt.event_type !== 'ZONE_EXIT' && (
                  evt.acknowledged ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400/70 shrink-0" />
                  ) : (
                    <button
                      onClick={() => acknowledge(evt)}
                      className="px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-foreground/5 hover:bg-emerald-500/20 text-foreground/60 hover:text-emerald-400 border border-foreground/10 transition-colors shrink-0"
                    >
                      Acknowledge
                    </button>
                  )
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** A number field that only commits on blur or Enter, so typing "1" on the way
 *  to "15" does not save a one-second rule and push it to every camera. */
function Num({ label, hint, value, min, max, step, disabled, allowEmpty, onCommit }: {
  label: string
  hint?: string
  value: number | null
  min: number
  max: number
  step: number
  disabled?: boolean
  allowEmpty?: boolean
  onCommit: (v: number | null) => void
}) {
  const [text, setText] = useState(value === null ? '' : String(value))
  useEffect(() => { setText(value === null ? '' : String(value)) }, [value])

  const commit = () => {
    if (text.trim() === '') {
      if (allowEmpty) onCommit(null)
      else setText(value === null ? '' : String(value))
      return
    }
    const n = Number(text)
    if (!Number.isFinite(n) || n < min || n > max) {
      setText(value === null ? '' : String(value))
      return
    }
    if (n !== value) onCommit(n)
  }

  return (
    <label className="block">
      <span className="block text-[10px] uppercase tracking-widest text-foreground/40">{label}</span>
      <input
        value={text}
        disabled={disabled}
        onChange={e => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
        className="mt-1 w-full px-2 py-1.5 rounded-lg bg-background border border-foreground/15 text-xs text-white focus:outline-none focus:border-amber-400/60 disabled:opacity-40"
      />
      {hint ? <span className="block mt-0.5 text-[9px] text-foreground/30">{hint}</span> : null}
    </label>
  )
}

function Select({ label, value, options, disabled, onChange }: {
  label: string
  value: string
  options: [string, string][]
  disabled?: boolean
  onChange: (v: string) => void
}) {
  return (
    <label className="block">
      <span className="block text-[10px] uppercase tracking-widest text-foreground/40">{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={e => onChange(e.target.value)}
        className="mt-1 w-full px-2 py-1.5 rounded-lg bg-background border border-foreground/15 text-xs text-white focus:outline-none focus:border-amber-400/60 disabled:opacity-40"
      >
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  )
}

/**
 * Commissioning check. Enter a position and the server answers whether it
 * would alert, and if not, which of the four possible reasons applies —
 * without anybody having to walk into the restricted area to find out.
 */
function ZoneTester({ zoneId }: { zoneId: string }) {
  const [x, setX] = useState('640')
  const [y, setY] = useState('600')
  const [result, setResult] = useState<{ would_alert: boolean; reason: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async () => {
    setBusy(true)
    try {
      const res = await api.post(`/api/zones/${zoneId}/test`, { point: [Number(x), Number(y)] })
      setResult({ would_alert: res.data.would_alert, reason: res.data.reason })
    } catch (err: any) {
      setResult({ would_alert: false, reason: err?.response?.data?.detail || 'Test failed.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Target className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
      <span className="text-[10px] uppercase tracking-widest text-foreground/40">Test a point</span>
      <input value={x} onChange={e => setX(e.target.value)} placeholder="x"
             className="w-16 px-2 py-1 rounded bg-background border border-foreground/15 text-[11px] text-white" />
      <input value={y} onChange={e => setY(e.target.value)} placeholder="y"
             className="w-16 px-2 py-1 rounded bg-background border border-foreground/15 text-[11px] text-white" />
      <button
        onClick={run}
        disabled={busy}
        className="px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-cyan-500/15 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 transition-colors disabled:opacity-40"
      >
        Check
      </button>
      {result && (
        <span className={cn('text-[10px]', result.would_alert ? 'text-danger' : 'text-foreground/50')}>
          {result.would_alert ? 'Would alert — ' : ''}{result.reason}
        </span>
      )}
    </div>
  )
}
