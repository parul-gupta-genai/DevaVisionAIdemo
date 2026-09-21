import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, Clock, Eye, EyeOff, RefreshCw, Shapes, Trash2, Undo2, X } from 'lucide-react'
import { api } from '@/api/api'
import { useToastStore } from '@/store/useToastStore'
import { computeContainViewport, VIDEO_W as VID_W, VIDEO_H as VID_H } from '@/utils/viewport'

// Matches the backend validator (MIN_ZONE_AREA in app/plugins/zones/geometry).
const MIN_ZONE_AREA = 500
const MAX_POINTS = 24
// How close (screen px) a click must be to the first vertex to close the shape.
const CLOSE_RADIUS = 14

export interface RestrictedZone {
  zone_id: string
  camera_id: string
  name: string
  points: [number, number][]
  is_active: boolean
  severity: string
  schedule_text: string
  armed_now: boolean
  min_dwell_sec: number
  loiter_sec?: number | null
  class_names: string[]
  evaluated_by?: string | null
}

interface Props {
  cameraId: string
  cameraName?: string
  onClose: () => void
}

const SEVERITY_STROKE: Record<string, string> = {
  critical: '#ef4444',
  warning: '#f59e0b',
  info: '#22d3ee',
}

function polygonArea(points: [number, number][]): number {
  let total = 0
  for (let i = 0; i < points.length; i++) {
    const [x1, y1] = points[i]
    const [x2, y2] = points[(i + 1) % points.length]
    total += x1 * y2 - x2 * y1
  }
  return Math.abs(total) / 2
}

/**
 * Full-card overlay for drawing restricted zones on the live video.
 *
 * Click to place each corner, click the first corner again (or press Enter) to
 * close the shape. Drag-a-rectangle would have been simpler, but a restricted
 * area on a real site is a loading bay or a walkway edge, not a rectangle, and
 * forcing it into one is how a zone ends up covering ground nobody meant to
 * restrict.
 *
 * Geometry only. Rules — schedule, dwell, which classes, severity — are set on
 * the Restricted Zones page, where there is room to explain what each does.
 */
export const RestrictedZoneEditor = memo(({ cameraId, cameraName, onClose }: Props) => {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const { addToast } = useToastStore()

  const [zones, setZones] = useState<RestrictedZone[]>([])
  const [draft, setDraft] = useState<[number, number][]>([])
  const [cursor, setCursor] = useState<[number, number] | null>(null)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)

  // ---- Load this camera's zones ---------------------------------------------
  // Drawing stays disabled until this succeeds. Unlike counting lines a save
  // here only adds one zone, so a failed load cannot wipe anything — but it
  // can silently duplicate a zone the operator already drew.
  const load = useCallback(async () => {
    setLoadFailed(false)
    try {
      const res = await api.get('/api/zones', { params: { camera_id: cameraId } })
      setZones(res.data || [])
      setLoaded(true)
    } catch {
      setLoadFailed(true)
      addToast({
        title: 'Zones unavailable',
        message: 'Could not load this camera’s zones — drawing is disabled until a retry succeeds.',
        type: 'danger',
      })
    }
  }, [cameraId, addToast])

  useEffect(() => { load() }, [load])

  // ---- screen <-> video mapping (same math as AnalyticsOverlay) -------------
  const getViewport = useCallback(() => {
    const canvas = canvasRef.current
    const width = canvas?.clientWidth || 1
    const height = canvas?.clientHeight || 1
    const videoEl = rootRef.current?.parentElement?.querySelector('video') as HTMLVideoElement | null
    return computeContainViewport(width, height, videoEl)
  }, [])

  const toVideoPoint = useCallback((clientX: number, clientY: number): [number, number] => {
    const canvas = canvasRef.current
    if (!canvas) return [0, 0]
    const rect = canvas.getBoundingClientRect()
    const { offsetX, offsetY, scaleX, scaleY } = getViewport()
    const vx = (clientX - rect.left - offsetX) / (scaleX || 1)
    const vy = (clientY - rect.top - offsetY) / (scaleY || 1)
    return [
      Math.round(Math.min(Math.max(vx, 0), VID_W)),
      Math.round(Math.min(Math.max(vy, 0), VID_H)),
    ]
  }, [getViewport])

  const draftArea = useMemo(
    () => (draft.length >= 3 ? polygonArea(draft) : 0),
    [draft]
  )
  const draftUsable = draft.length >= 3 && draftArea >= MIN_ZONE_AREA

  // ---- Canvas rendering ------------------------------------------------------
  const redraw = useCallback(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return

    const width = canvas.clientWidth
    const height = canvas.clientHeight
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width
      canvas.height = height
    }
    ctx.clearRect(0, 0, width, height)

    const { offsetX, offsetY, scaleX, scaleY } = getViewport()
    const mapX = (x: number) => offsetX + x * scaleX
    const mapY = (y: number) => offsetY + y * scaleY

    // Dim the letterbox bars so the drawable video area is obvious.
    ctx.fillStyle = 'rgba(0, 0, 0, 0.55)'
    if (offsetX > 0) {
      ctx.fillRect(0, 0, offsetX, height)
      ctx.fillRect(width - offsetX, 0, offsetX, height)
    }
    if (offsetY > 0) {
      ctx.fillRect(0, 0, width, offsetY)
      ctx.fillRect(0, height - offsetY, width, offsetY)
    }

    const tracePolygon = (points: [number, number][]) => {
      ctx.beginPath()
      points.forEach(([x, y], i) => {
        if (i === 0) ctx.moveTo(mapX(x), mapY(y))
        else ctx.lineTo(mapX(x), mapY(y))
      })
    }

    for (const zone of zones) {
      const points = (zone.points || []) as [number, number][]
      if (points.length < 3) continue
      // A zone that is off, or outside its schedule, is drawn grey. An
      // enforcing zone and a sleeping one must never look the same.
      const live = zone.is_active && zone.armed_now
      const stroke = live ? (SEVERITY_STROKE[zone.severity] || '#f59e0b') : '#94a3b8'
      tracePolygon(points)
      ctx.closePath()
      ctx.fillStyle = live ? `${stroke}22` : 'rgba(148,163,184,0.10)'
      ctx.fill()
      ctx.strokeStyle = stroke
      ctx.lineWidth = 2
      ctx.setLineDash(live ? [] : [6, 4])
      ctx.stroke()
      ctx.setLineDash([])

      const top = points.reduce((a, b) => (b[1] < a[1] ? b : a), points[0])
      const label = `${zone.name}${live ? '' : zone.is_active ? ' · off-schedule' : ' · disabled'}`
      ctx.font = 'bold 11px Inter, sans-serif'
      const w = ctx.measureText(label).width + 10
      ctx.fillStyle = 'rgba(0,0,0,0.72)'
      ctx.fillRect(mapX(top[0]) - 4, mapY(top[1]) - 20, w, 16)
      ctx.fillStyle = live ? stroke : '#cbd5e1'
      ctx.fillText(label, mapX(top[0]) + 1, mapY(top[1]) - 8)
    }

    if (draft.length > 0) {
      const preview: [number, number][] =
        cursor && draft.length >= 1 ? [...draft, cursor] : draft
      tracePolygon(preview)
      if (draft.length >= 3) {
        ctx.closePath()
        ctx.fillStyle = 'rgba(56, 189, 248, 0.16)'
        ctx.fill()
      }
      ctx.strokeStyle = '#38bdf8'
      ctx.lineWidth = 2.5
      ctx.setLineDash([5, 4])
      ctx.stroke()
      ctx.setLineDash([])

      draft.forEach(([x, y], i) => {
        ctx.beginPath()
        ctx.arc(mapX(x), mapY(y), i === 0 ? 6 : 4, 0, Math.PI * 2)
        ctx.fillStyle = i === 0 ? '#22d3ee' : '#38bdf8'
        ctx.fill()
        if (i === 0 && draft.length >= 3) {
          ctx.strokeStyle = '#22d3ee'
          ctx.lineWidth = 1.5
          ctx.beginPath()
          ctx.arc(mapX(x), mapY(y), 10, 0, Math.PI * 2)
          ctx.stroke()
        }
      })
    }
  }, [zones, draft, cursor, getViewport])

  useEffect(() => { redraw() }, [redraw])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const observer = new ResizeObserver(() => redraw())
    observer.observe(canvas)
    const videoEl = rootRef.current?.parentElement?.querySelector('video')
    videoEl?.addEventListener('loadedmetadata', redraw)
    return () => {
      observer.disconnect()
      videoEl?.removeEventListener('loadedmetadata', redraw)
    }
  }, [redraw])

  // ---- Persistence -----------------------------------------------------------
  const save = useCallback(async () => {
    if (!draftUsable || saving) return
    setSaving(true)
    try {
      const body = {
        camera_id: cameraId,
        name: name.trim() || `Zone ${zones.length + 1}`,
        points: draft,
      }
      const res = await api.post('/api/zones', body)
      setZones([...zones, res.data])
      setDraft([])
      setCursor(null)
      setName('')
      addToast({
        title: 'Zone live',
        message: `${res.data.name} is now monitored — alerts after ${res.data.min_dwell_sec}s inside. Set its schedule on the Restricted Zones page.`,
        type: 'success',
      })
    } catch (err: any) {
      addToast({
        title: 'Could not save zone',
        message: err?.response?.data?.detail || 'The server rejected this zone.',
        type: 'danger',
      })
    } finally {
      setSaving(false)
    }
  }, [draftUsable, saving, cameraId, name, draft, zones, addToast])

  // ---- Drawing interactions --------------------------------------------------
  const nearFirstPoint = (clientX: number, clientY: number) => {
    if (draft.length < 3) return false
    const canvas = canvasRef.current
    if (!canvas) return false
    const rect = canvas.getBoundingClientRect()
    const { offsetX, offsetY, scaleX, scaleY } = getViewport()
    const fx = rect.left + offsetX + draft[0][0] * scaleX
    const fy = rect.top + offsetY + draft[0][1] * scaleY
    return Math.hypot(clientX - fx, clientY - fy) <= CLOSE_RADIUS
  }

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (saving || !loaded) return
    if (nearFirstPoint(e.clientX, e.clientY)) {
      // The ring drawn around the first corner is the affordance for "click
      // here to finish"; it has to actually finish, or the shape can never be
      // closed by the gesture the UI advertises.
      setCursor(null)
      if (draftUsable) void save()
      else addToast({
        title: 'Zone too small',
        message: 'Drag the corners further apart — this encloses almost no ground.',
        type: 'warning',
      })
      return
    }
    if (draft.length >= MAX_POINTS) {
      addToast({
        title: 'Too many corners',
        message: `A zone can have at most ${MAX_POINTS} corners.`,
        type: 'warning',
      })
      return
    }
    setDraft([...draft, toVideoPoint(e.clientX, e.clientY)])
  }

  const handleMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (draft.length === 0) return
    setCursor(toVideoPoint(e.clientX, e.clientY))
  }


  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (draft.length > 0) { setDraft([]); setCursor(null) }
        else onClose()
      }
      if (e.key === 'Enter' && draftUsable && !saving) void save()
      if (e.key === 'Backspace' && draft.length > 0) {
        e.preventDefault()
        setDraft(draft.slice(0, -1))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [draft, draftUsable, saving, save, onClose])

  const remove = async (zone: RestrictedZone) => {
    setSaving(true)
    try {
      await api.delete(`/api/zones/${zone.zone_id}`)
      setZones(zones.filter(z => z.zone_id !== zone.zone_id))
      addToast({
        title: 'Zone removed',
        message: `${zone.name} is no longer monitored. Its past events are kept.`,
        type: 'success',
      })
    } catch {
      addToast({ title: 'Delete failed', message: 'Could not remove the zone.', type: 'danger' })
      await load()
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async (zone: RestrictedZone) => {
    setSaving(true)
    try {
      const res = await api.put(`/api/zones/${zone.zone_id}`, { is_active: !zone.is_active })
      setZones(zones.map(z => (z.zone_id === zone.zone_id ? res.data : z)))
    } catch {
      addToast({ title: 'Update failed', message: 'Could not change the zone.', type: 'danger' })
      await load()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div ref={rootRef} className="absolute inset-0 z-40" onClick={(e) => e.stopPropagation()}>
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full touch-none"
        style={{ cursor: loaded ? 'crosshair' : 'progress' }}
        onClick={handleClick}
        onMouseMove={handleMove}
        onMouseLeave={() => setCursor(null)}
      />

      <div className="absolute top-3 left-3 w-80 max-w-[88%] bg-slate-950/85 backdrop-blur-md border border-amber-500/30 rounded-xl shadow-2xl overflow-hidden pointer-events-auto">
        <div className="px-3 py-2.5 flex items-center justify-between border-b border-foreground/10 bg-amber-500/10">
          <div className="flex items-center gap-2 text-amber-300">
            <Shapes className="w-4 h-4" />
            <span className="text-xs font-bold uppercase tracking-widest">Restricted Zones</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-foreground/10 text-foreground/60 hover:text-white transition-colors"
            title="Close editor"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-3 py-2 text-[11px] leading-relaxed text-foreground/70">
          Click each corner of the area, then click the first corner again to close it.
          <span className="block mt-0.5 text-foreground/45">
            Esc clears the shape · Backspace removes the last corner · Enter saves.
          </span>
          {cameraName ? <span className="block mt-1 text-foreground/40">Camera: {cameraName}</span> : null}
        </div>

        {draft.length > 0 && (
          <div className="px-3 pb-2 space-y-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={`Zone ${zones.length + 1} — e.g. Switchyard`}
              className="w-full px-2 py-1.5 rounded-lg bg-foreground/5 border border-foreground/15 text-[11px] text-white placeholder:text-foreground/30 focus:outline-none focus:border-amber-400/60"
            />
            <div className="flex items-center gap-2">
              <button
                onClick={save}
                disabled={!draftUsable || saving}
                className="flex-1 flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-amber-500/90 hover:bg-amber-400 text-slate-950 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Check className="w-3 h-3" />
                {draft.length < 3
                  ? `${3 - draft.length} more corner${draft.length === 2 ? '' : 's'}`
                  : !draftUsable ? 'Too small' : 'Save zone'}
              </button>
              <button
                onClick={() => setDraft(draft.slice(0, -1))}
                className="p-1.5 rounded-lg bg-foreground/5 hover:bg-foreground/15 text-foreground/70 border border-foreground/10 transition-colors"
                title="Undo last corner"
              >
                <Undo2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        <div className="px-3 pb-2 flex flex-col gap-1.5 max-h-44 overflow-y-auto">
          {!loaded ? (
            loadFailed ? (
              <button
                onClick={load}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold bg-danger/10 hover:bg-danger/20 text-danger border border-danger/30 transition-colors"
              >
                <RefreshCw className="w-3 h-3" /> Failed to load zones — Retry
              </button>
            ) : (
              <div className="text-[11px] text-foreground/40 py-1">Loading…</div>
            )
          ) : zones.length === 0 ? (
            <div className="text-[11px] text-foreground/50 py-1 italic">
              No zone on this camera — nothing is being monitored here. Draw one to start.
            </div>
          ) : (
            zones.map((zone) => (
              <div
                key={zone.zone_id}
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-foreground/5 border border-foreground/10 text-[11px] text-white"
              >
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{
                    background: zone.is_active && zone.armed_now
                      ? SEVERITY_STROKE[zone.severity] || '#f59e0b'
                      : '#64748b',
                  }}
                />
                <div className="flex-1 min-w-0">
                  <div className="truncate font-semibold">{zone.name}</div>
                  <div className="truncate text-[9px] text-foreground/45 flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5" />
                    {zone.is_active
                      ? (zone.armed_now ? `Armed · ${zone.schedule_text}` : `Off-schedule · ${zone.schedule_text}`)
                      : 'Disabled'}
                  </div>
                </div>
                <button
                  onClick={() => toggleActive(zone)}
                  disabled={saving}
                  className="p-1 rounded hover:bg-foreground/15 text-foreground/60 transition-colors disabled:opacity-40"
                  title={zone.is_active ? 'Disable this zone' : 'Enable this zone'}
                >
                  {zone.is_active ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                </button>
                <button
                  onClick={() => remove(zone)}
                  disabled={saving}
                  className="p-1 rounded hover:bg-danger/20 text-danger transition-colors disabled:opacity-40"
                  title="Delete zone"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="px-3 py-2.5 border-t border-foreground/10 flex items-center justify-between gap-2">
          <a
            href="/restricted-zones"
            className="text-[10px] font-bold uppercase tracking-wider text-amber-300/80 hover:text-amber-200 transition-colors"
          >
            Rules &amp; schedule →
          </a>
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-amber-500/90 hover:bg-amber-400 text-slate-950 transition-colors shadow-[0_0_12px_rgba(245,158,11,0.35)]"
          >
            <Check className="w-3 h-3" /> Done
          </button>
        </div>

        {saving && <div className="absolute inset-x-0 bottom-0 h-0.5 bg-amber-400/80 animate-pulse" />}
      </div>
    </div>
  )
})

RestrictedZoneEditor.displayName = 'RestrictedZoneEditor'
