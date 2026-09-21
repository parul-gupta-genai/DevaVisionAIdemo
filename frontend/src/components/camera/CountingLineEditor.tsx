import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { X, ArrowLeftRight, Trash2, RotateCcw, Check, Spline, RefreshCw } from 'lucide-react'
import { api } from '@/api/api'
import { useToastStore } from '@/store/useToastStore'
import { computeContainViewport, VIDEO_W as VID_W, VIDEO_H as VID_H } from '@/utils/viewport'

// Minimum drawn length (video px) — matches the backend validator (>= 8).
const MIN_LINE_LEN = 24

export interface CountingLine {
  id: string
  name: string
  start: [number, number]
  end: [number, number]
}

interface CountingLineEditorProps {
  cameraId: string
  cameraName?: string
  onClose: () => void
}

interface Viewport {
  offsetX: number
  offsetY: number
  scaleX: number
  scaleY: number
}

/**
 * Full-card overlay that lets the user drag counting lines directly on the
 * live video. Every finished drag is saved immediately via POST /api/config
 * (COUNTING_LINES), which the backend pushes to the running DeepStream plugin
 * engine over Redis — the line starts counting on the next frame, with no
 * camera/pipeline restart. Coordinate mapping mirrors AnalyticsOverlay's
 * object-contain math so drawn pixels land exactly where the plugin counts.
 */
export const CountingLineEditor = memo(({ cameraId, cameraName, onClose }: CountingLineEditorProps) => {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const { addToast } = useToastStore()

  const [lines, setLines] = useState<CountingLine[]>([])
  const [usingDefault, setUsingDefault] = useState(true)
  const [draft, setDraft] = useState<{ start: [number, number]; end: [number, number] } | null>(null)
  const [saving, setSaving] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)

  // ---- Load the camera's current custom lines --------------------------------
  // Drawing stays disabled until this succeeds: persisting after a failed
  // load would silently overwrite the camera's existing lines with just the
  // newly drawn one.
  const loadLines = useCallback(async () => {
    setLoadFailed(false)
    setLoaded(false)
    try {
      const res = await api.get(`/api/config?t=${Date.now()}`)
      const entry = res.data?.COUNTING_LINES?.[cameraId]
      if (Array.isArray(entry)) {
        setLines(entry.filter((l: any) => Array.isArray(l?.start) && Array.isArray(l?.end)))
        setUsingDefault(false)
      } else {
        setLines([])
        setUsingDefault(true)
      }
      setLoaded(true)
    } catch {
      setLoadFailed(true)
      addToast({ title: 'Config Error', message: 'Could not load counting lines — drawing disabled until retry succeeds.', type: 'danger' })
    }
  }, [cameraId, addToast])

  useEffect(() => { loadLines() }, [loadLines])

  // ---- Persistence -----------------------------------------------------------
  const persist = useCallback(async (nextLines: CountingLine[] | null, successMsg: string) => {
    setSaving(true)
    try {
      await api.post('/api/config', {
        updates: { COUNTING_LINES: { [cameraId]: nextLines } }
      })
      addToast({ title: 'Counting Line Live', message: successMsg, type: 'success' })
    } catch (err: any) {
      addToast({
        title: 'Save Failed',
        message: err?.response?.data?.detail || 'Could not save counting lines.',
        type: 'danger'
      })
      // Re-sync from the server so the UI never lies about what is active;
      // if that also fails, loadFailed blocks further drawing.
      await loadLines()
    } finally {
      setSaving(false)
    }
  }, [cameraId, addToast, loadLines])

  // ---- screen <-> video mapping (same math as AnalyticsOverlay) --------------
  const getViewport = useCallback((): Viewport => {
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

    const drawArrow = (a: [number, number], b: [number, number], color: string) => {
      // Same right-hand rule as the backend: normal (-dy, dx) marks the IN side.
      const dx = b[0] - a[0]
      const dy = b[1] - a[1]
      const len = Math.hypot(dx, dy) || 1
      const nx = -dy / len
      const ny = dx / len
      const mx = (a[0] + b[0]) / 2
      const my = (a[1] + b[1]) / 2
      const tip: [number, number] = [mx + nx * 34, my + ny * 34]

      ctx.beginPath()
      ctx.moveTo(mapX(mx), mapY(my))
      ctx.lineTo(mapX(tip[0]), mapY(tip[1]))
      const barb = 10
      const angle = Math.atan2(-ny, -nx)
      for (const s of [Math.PI / 6, -Math.PI / 6]) {
        ctx.moveTo(mapX(tip[0]), mapY(tip[1]))
        ctx.lineTo(
          mapX(tip[0] + Math.cos(angle + s) * barb),
          mapY(tip[1] + Math.sin(angle + s) * barb)
        )
      }
      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.stroke()

      ctx.font = 'bold 11px Inter, sans-serif'
      ctx.fillStyle = color
      ctx.fillText('IN', mapX(tip[0] + nx * 10) - 6, mapY(tip[1] + ny * 10) + 4)
    }

    const drawLine = (line: CountingLine, index: number) => {
      const a = line.start
      const b = line.end
      ctx.save()
      ctx.setLineDash([8, 5])
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)'
      ctx.lineWidth = 2.5
      ctx.shadowColor = 'rgba(0, 240, 255, 0.8)'
      ctx.shadowBlur = 5
      ctx.beginPath()
      ctx.moveTo(mapX(a[0]), mapY(a[1]))
      ctx.lineTo(mapX(b[0]), mapY(b[1]))
      ctx.stroke()
      ctx.restore()

      // Endpoint handles: circle at start, square at end (shows direction).
      ctx.fillStyle = '#22d3ee'
      ctx.beginPath()
      ctx.arc(mapX(a[0]), mapY(a[1]), 4.5, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillRect(mapX(b[0]) - 4, mapY(b[1]) - 4, 8, 8)

      drawArrow(a, b, '#34d399')

      ctx.font = 'bold 11px Inter, sans-serif'
      const label = `${index + 1}. ${line.name}`
      const tx = mapX(Math.min(a[0], b[0])) + 6
      const ty = mapY(Math.min(a[1], b[1])) - 8
      ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
      ctx.fillRect(tx - 3, ty - 11, ctx.measureText(label).width + 8, 15)
      ctx.fillStyle = '#ffffff'
      ctx.fillText(label, tx, ty)
    }

    lines.forEach(drawLine)

    if (draft) {
      ctx.save()
      ctx.strokeStyle = '#fbbf24'
      ctx.lineWidth = 2.5
      ctx.setLineDash([4, 4])
      ctx.beginPath()
      ctx.moveTo(mapX(draft.start[0]), mapY(draft.start[1]))
      ctx.lineTo(mapX(draft.end[0]), mapY(draft.end[1]))
      ctx.stroke()
      ctx.restore()
      drawArrow(draft.start, draft.end, '#fbbf24')
    }
  }, [lines, draft, getViewport])

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

  // ---- Drawing interactions --------------------------------------------------
  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    // No drawing until the current lines loaded — persisting on top of an
    // unknown server state would wipe the camera's existing lines.
    if (e.button !== 0 || saving || !loaded) return
    e.currentTarget.setPointerCapture(e.pointerId)
    const p = toVideoPoint(e.clientX, e.clientY)
    setDraft({ start: p, end: p })
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!draft) return
    setDraft({ start: draft.start, end: toVideoPoint(e.clientX, e.clientY) })
  }

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!draft) return
    const end = toVideoPoint(e.clientX, e.clientY)
    const length = Math.hypot(end[0] - draft.start[0], end[1] - draft.start[1])
    const start = draft.start
    setDraft(null)
    if (length < MIN_LINE_LEN) return

    const newLine: CountingLine = {
      id: `line-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: `Line ${lines.length + 1}`,
      start,
      end,
    }
    const next = [...lines, newLine]
    setLines(next)
    setUsingDefault(false)
    persist(next, `${newLine.name} is now counting IN/OUT crossings.`)
  }

  const flipLine = (id: string) => {
    const next = lines.map(l => l.id === id ? { ...l, start: l.end, end: l.start } : l)
    setLines(next)
    persist(next, 'IN/OUT direction flipped.')
  }

  const deleteLine = (id: string) => {
    const next = lines.filter(l => l.id !== id)
    setLines(next)
    setUsingDefault(false)
    persist(next, next.length ? 'Line removed.' : 'All lines removed — crossing counting is off for this camera.')
  }

  const resetToDefault = () => {
    setLines([])
    setUsingDefault(true)
    persist(null, 'Camera reset to the default entry line.')
  }

  return (
    <div
      ref={rootRef}
      className="absolute inset-0 z-40"
      onClick={(e) => e.stopPropagation()}
    >
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full touch-none"
        style={{ cursor: 'crosshair' }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={() => setDraft(null)}
      />

      {/* Control panel */}
      <div className="absolute top-3 left-3 w-72 max-w-[85%] bg-slate-950/85 backdrop-blur-md border border-cyan-500/30 rounded-xl shadow-2xl overflow-hidden pointer-events-auto">
        <div className="px-3 py-2.5 flex items-center justify-between border-b border-foreground/10 bg-cyan-500/10">
          <div className="flex items-center gap-2 text-cyan-300">
            <Spline className="w-4 h-4" />
            <span className="text-xs font-bold uppercase tracking-widest">People Counting Lines</span>
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
          Drag on the live video to draw a counting line — it goes live instantly, no stream restart.
          The <span className="text-emerald-400 font-bold">green arrow</span> marks the IN direction; use ⇄ to flip it.
          {cameraName ? <span className="block mt-1 text-foreground/40">Camera: {cameraName}</span> : null}
        </div>

        <div className="px-3 pb-2 flex flex-col gap-1.5 max-h-40 overflow-y-auto">
          {!loaded ? (
            loadFailed ? (
              <button
                onClick={loadLines}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold bg-danger/10 hover:bg-danger/20 text-danger border border-danger/30 transition-colors"
              >
                <RefreshCw className="w-3 h-3" /> Failed to load current lines — Retry
              </button>
            ) : (
              <div className="text-[11px] text-foreground/40 py-1">Loading…</div>
            )
          ) : lines.length === 0 ? (
            <div className="text-[11px] text-foreground/50 py-1 italic">
              {usingDefault
                ? 'Using the default entry line — draw to replace it.'
                : 'No lines — crossing counting is off. Draw one to start.'}
            </div>
          ) : (
            lines.map((line, i) => (
              <div
                key={line.id}
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-foreground/5 border border-foreground/10 text-[11px] text-white"
              >
                <span className="w-4 h-4 rounded-full bg-cyan-500/20 text-cyan-300 flex items-center justify-center font-bold text-[9px] shrink-0">
                  {i + 1}
                </span>
                <span className="flex-1 truncate font-semibold">{line.name}</span>
                <button
                  onClick={() => flipLine(line.id)}
                  disabled={saving}
                  className="p-1 rounded hover:bg-emerald-500/20 text-emerald-400 transition-colors disabled:opacity-40"
                  title="Flip IN/OUT direction"
                >
                  <ArrowLeftRight className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => deleteLine(line.id)}
                  disabled={saving}
                  className="p-1 rounded hover:bg-danger/20 text-danger transition-colors disabled:opacity-40"
                  title="Delete line"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="px-3 py-2.5 border-t border-foreground/10 flex items-center justify-between gap-2">
          <button
            onClick={resetToDefault}
            disabled={saving || !loaded || (usingDefault && lines.length === 0)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-foreground/5 hover:bg-foreground/15 text-foreground/70 hover:text-white border border-foreground/10 transition-colors disabled:opacity-40"
            title="Remove custom lines and restore the default entry line"
          >
            <RotateCcw className="w-3 h-3" /> Default
          </button>
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-cyan-500/90 hover:bg-cyan-400 text-slate-950 transition-colors shadow-[0_0_12px_rgba(34,211,238,0.4)]"
          >
            <Check className="w-3 h-3" /> Done
          </button>
        </div>

        {saving && (
          <div className="absolute inset-x-0 bottom-0 h-0.5 bg-cyan-400/80 animate-pulse" />
        )}
      </div>
    </div>
  )
})

CountingLineEditor.displayName = 'CountingLineEditor'
