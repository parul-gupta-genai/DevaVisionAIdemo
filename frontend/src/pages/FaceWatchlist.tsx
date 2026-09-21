import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertOctagon, Camera, Check, Clock, Eye, Loader2, Plus, Search, ShieldAlert, Star, Trash2, User, X,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/utils'
import { api } from '@/api/api'

type Entry = {
  entry_id: string
  person_id: string
  person_name?: string
  person_code?: string
  photo?: string
  category: string
  severity: string
  reason?: string
  active_until?: string
  camera_ids?: string[]
  is_active: boolean
}

type Hit = {
  event_id: string
  person_id?: string
  person_name?: string
  category?: string
  severity?: string
  camera_id?: string
  camera_name?: string
  timestamp: string
  similarity?: number
  snapshot_file?: string
}

const CATEGORIES = ['BLACKLIST', 'VIP', 'PERSON_OF_INTEREST', 'EX_EMPLOYEE']

const severityTone = (s?: string) =>
  s === 'critical' ? 'bg-danger/20 text-danger border-danger/40'
    : s === 'warning' ? 'bg-warning/20 text-warning border-warning/40'
      : 'bg-info/20 text-info border-info/40'

const categoryIcon = (c?: string) => (c === 'VIP' ? Star : ShieldAlert)

const resolvePhotoUrl = (p?: string | null) => {
  if (!p) return null
  if (p.startsWith('http://') || p.startsWith('https://') || p.startsWith('data:')) return p
  return p.startsWith('/') ? p : `/${p}`
}

export function FaceWatchlist() {
  const [entries, setEntries] = useState<Entry[]>([])
  const [live, setLive] = useState<any>(null)
  const [history, setHistory] = useState<Hit[]>([])
  const [windowMin, setWindowMin] = useState(60)
  const [categoryFilter, setCategoryFilter] = useState('')
  const [search, setSearch] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [forbidden, setForbidden] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [w, m, h] = await Promise.all([
        api.get('/api/face/watchlist', { params: categoryFilter ? { category: categoryFilter } : {} }),
        api.get('/api/face/monitoring/live', { params: { minutes: windowMin } }),
        api.get('/api/face/events', {
          params: { event_type: 'WATCHLIST_HIT', limit: 100, ...(categoryFilter ? { category: categoryFilter } : {}) },
        }),
      ])
      setEntries(w.data || [])
      setLive(m.data)
      setHistory(h.data?.items || [])
    } catch (e: any) {
      if (e?.response?.status === 403) setForbidden(true)
      else setError(e?.response?.data?.detail?.message || e?.message || 'Failed to load watchlist')
    }
  }, [windowMin, categoryFilter])

  useEffect(() => {
    load()
    // Watchlist hits are the reason somebody has this page open; poll so a
    // hit appears without the operator refreshing.
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [load])

  const remove = async (entryId: string) => {
    try {
      await api.delete(`/api/face/watchlist/${entryId}`)
      load()
    } catch (e: any) {
      setError(e?.response?.status === 403
        ? 'Your role cannot change the watchlist.'
        : 'Could not remove that entry.')
    }
  }

  const shown = useMemo(() => {
    if (!search.trim()) return entries
    const q = search.toLowerCase()
    return entries.filter(e =>
      (e.person_name || '').toLowerCase().includes(q) ||
      (e.person_code || '').toLowerCase().includes(q))
  }, [entries, search])

  if (forbidden) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-12 text-center shadow-sm">
        <ShieldAlert className="w-10 h-10 text-warning mx-auto mb-3" />
        <h2 className="text-lg font-bold text-slate-900">Not authorised</h2>
        <p className="text-sm text-slate-500 mt-1">
          Face monitoring requires the <code>face:read</code> permission.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-danger" /> Face Monitoring &amp; Watchlist
          </h1>
          <p className="text-sm text-slate-500">
            Alerts raised when a watchlisted face is seen on any camera
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)}
                  className="bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary/40">
            <option value="">All categories</option>
            {CATEGORIES.map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
          </select>
          <select value={windowMin} onChange={e => setWindowMin(Number(e.target.value))}
                  className="bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary/40">
            <option value={15}>Last 15 min</option>
            <option value={60}>Last hour</option>
            <option value={480}>Last 8 hours</option>
            <option value={1440}>Last 24 hours</option>
          </select>
          <button onClick={() => setAddOpen(true)}
                  className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-danger/10 text-danger text-sm font-semibold hover:bg-danger/20 transition-colors border border-danger/20 cursor-pointer">
            <Plus className="w-4 h-4" /> Add to watchlist
          </button>
        </div>
      </div>

      {error && (
        <div className="border border-danger/40 bg-danger/10 rounded-xl p-4 text-sm text-danger">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
          <div className="text-3xl font-bold text-danger">{live?.total_hits ?? '—'}</div>
          <div className="text-xs text-slate-500 uppercase tracking-wide mt-1">
            Hits in window
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
          <div className="text-3xl font-bold text-slate-900">{live?.watchlist_size ?? entries.length}</div>
          <div className="text-xs text-slate-500 uppercase tracking-wide mt-1">
            People watchlisted
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
          <div className="text-3xl font-bold text-slate-900">
            {Object.keys(live?.by_camera || {}).length}
          </div>
          <div className="text-xs text-slate-500 uppercase tracking-wide mt-1">
            Cameras with hits
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(live?.by_category || {}).map(([c, n]) => (
              <span key={c} className="px-2 py-1 rounded bg-slate-100 text-xs font-medium text-slate-800">
                {c.replace(/_/g, ' ')} {String(n)}
              </span>
            ))}
            {!Object.keys(live?.by_category || {}).length && (
              <span className="text-sm text-slate-500">No hits</span>
            )}
          </div>
          <div className="text-xs text-slate-500 uppercase tracking-wide mt-2">
            By category
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
          <div className="p-4 border-b border-slate-200 flex items-center gap-2 bg-slate-50/70">
            <AlertOctagon className="w-4 h-4 text-danger" />
            <h3 className="text-sm font-semibold text-slate-900">Recent hits</h3>
            <span className="ml-auto text-xs text-slate-500">{history.length}</span>
          </div>
          <div className="divide-y divide-slate-100 max-h-[520px] overflow-y-auto">
            {history.map(h => {
              const snap = resolvePhotoUrl(h.snapshot_file)
              return (
                <div key={h.event_id} className="p-4 flex items-center gap-4 hover:bg-slate-50/80">
                  {snap ? (
                    <img src={snap} alt=""
                         className="w-16 h-16 rounded-lg object-cover border border-danger/30" />
                  ) : (
                    <div className="w-16 h-16 rounded-lg bg-slate-100 flex items-center justify-center">
                      <Eye className="w-5 h-5 text-slate-400" />
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-slate-900 truncate">
                      {h.person_name || 'Unknown'}
                    </div>
                    <div className="text-xs text-slate-500 flex items-center gap-3 mt-0.5">
                      <span className="flex items-center gap-1">
                        <Camera className="w-3 h-3" />{h.camera_name || h.camera_id || '—'}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(h.timestamp).toLocaleString()}
                      </span>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <span className={cn('px-2 py-1 rounded text-[10px] font-bold border',
                      severityTone(h.severity))}>
                      {h.category?.replace(/_/g, ' ') || 'HIT'}
                    </span>
                    {h.similarity != null && (
                      <div className="text-xs text-slate-500 mt-1 font-mono">
                        {h.similarity.toFixed(2)}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
            {history.length === 0 && (
              <div className="p-12 text-center text-slate-500 text-sm">
                No watchlist hits recorded.
              </div>
            )}
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
          <div className="p-4 border-b border-slate-200 flex items-center gap-3 bg-slate-50/70">
            <Search className="w-4 h-4 text-slate-400" />
            <input value={search} onChange={e => setSearch(e.target.value)}
                   placeholder="Search the watchlist"
                   className="bg-transparent outline-none text-sm text-slate-900 placeholder:text-slate-400 flex-1" />
            <span className="text-xs text-slate-500">{shown.length}</span>
          </div>
          <div className="divide-y divide-slate-100 max-h-[520px] overflow-y-auto">
            {shown.map(e => {
              const Icon = categoryIcon(e.category)
              const photoUrl = resolvePhotoUrl(e.photo)
              return (
                <div key={e.entry_id} className="p-4 flex items-center gap-4 hover:bg-slate-50/80 group">
                  {photoUrl ? (
                    <img src={photoUrl} alt="" className="w-12 h-12 rounded-lg object-cover border border-slate-200" />
                  ) : (
                    <div className="w-12 h-12 rounded-lg bg-slate-100 flex items-center justify-center">
                      <Icon className="w-5 h-5 text-slate-400" />
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-slate-900 truncate">
                      {e.person_name || e.person_id}
                    </div>
                    <div className="text-xs text-slate-500 truncate">
                      {e.reason || 'No reason recorded'}
                    </div>
                    {e.camera_ids?.length ? (
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        Limited to {e.camera_ids.length} camera(s)
                      </div>
                    ) : null}
                  </div>
                  <span className={cn('px-2 py-1 rounded text-[10px] font-bold border shrink-0',
                    severityTone(e.severity))}>
                    {e.category.replace(/_/g, ' ')}
                  </span>
                  <button onClick={() => remove(e.entry_id)}
                          title="Remove from watchlist"
                          className="opacity-0 group-hover:opacity-100 transition-opacity p-2 rounded-lg hover:bg-danger/20 text-danger cursor-pointer">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              )
            })}
            {shown.length === 0 && (
              <div className="p-12 text-center text-slate-500 text-sm">
                Nobody is on the watchlist.
              </div>
            )}
          </div>
        </div>
      </div>

      {addOpen && <AddDialog onClose={() => { setAddOpen(false); load() }} />}
    </div>
  )
}

function AddDialog({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [people, setPeople] = useState<any[]>([])
  const [selected, setSelected] = useState<any>(null)
  const [category, setCategory] = useState('BLACKLIST')
  const [severity, setSeverity] = useState('critical')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const res = await api.get('/api/face/persons',
          { params: { search: query || undefined, limit: 20 } })
        const items = res.data?.items || []
        setPeople(items)
        if (items.length > 0 && !selected) {
          setSelected(items[0])
        }
      } catch { /* search is best-effort */ }
    }, 200)
    return () => clearTimeout(t)
  }, [query])

  const submit = async () => {
    if (!selected) {
      setError("Please click on a person from the list below to select them.")
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.post('/api/face/watchlist', {
        person_id: selected.person_id, category, severity, reason: reason || null,
      })
      onClose()
    } catch (e: any) {
      const d = e?.response?.data?.detail
      setError(e?.response?.status === 403
        ? 'Your role cannot change the watchlist.'
        : (typeof d === 'string' ? d : d?.message || 'Could not add that person.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4"
         onClick={onClose}>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                  onClick={e => e.stopPropagation()}
                  className="bg-white border border-slate-200 shadow-2xl rounded-2xl p-6 w-full max-w-lg space-y-4 text-slate-900">
        <div className="flex items-center justify-between pb-2 border-b border-slate-100">
          <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-danger" /> Add to Watchlist
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 transition-colors p-1 rounded-md cursor-pointer">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">Search Enrolled Person</label>
          <input value={query} onChange={e => setQuery(e.target.value)}
                 placeholder="Search enrolled people by name or code..."
                 className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary" />
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">Select Candidate ({people.length})</label>
          <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-200 divide-y divide-slate-100 bg-slate-50/50">
            {people.map(p => {
              const photoUrl = resolvePhotoUrl(p.photo)
              const isSelected = selected?.person_id === p.person_id
              const initial = p.name ? p.name.trim().charAt(0).toUpperCase() : 'U'
              return (
                <button key={p.person_id} onClick={() => setSelected(p)}
                        type="button"
                        className={cn('w-full text-left px-3 py-2.5 flex items-center gap-3 transition-colors cursor-pointer',
                          isSelected ? 'bg-blue-50/90 border-l-4 border-blue-600' : 'hover:bg-slate-100')}>
                  <div className="w-10 h-10 rounded-lg overflow-hidden shrink-0 border border-slate-200 bg-slate-100 flex items-center justify-center">
                    {photoUrl ? (
                      <img src={photoUrl} alt={p.name} className="w-full h-full object-cover"
                           onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                    ) : null}
                    <span className="font-bold text-sm text-slate-600">{initial}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-slate-900 truncate flex items-center gap-2">
                      {p.name}
                      {isSelected && <span className="text-[10px] bg-blue-600 text-white font-bold px-1.5 py-0.5 rounded">Selected</span>}
                    </div>
                    <div className="text-[11px] text-slate-500 font-mono">
                      {p.person_code || p.person_type}
                      {!p.enrolled && ' · no face embedding'}
                    </div>
                  </div>
                  {isSelected && <Check className="w-4 h-4 text-blue-600 shrink-0" />}
                </button>
              )
            })}
            {people.length === 0 && (
              <div className="px-3 py-6 text-center text-xs text-slate-500">
                No enrolled people match.
              </div>
            )}
          </div>
        </div>

        {selected && (
          <div className="p-3 bg-blue-50/80 border border-blue-200 rounded-xl flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg overflow-hidden border-2 border-blue-500 bg-white flex items-center justify-center shrink-0">
              {resolvePhotoUrl(selected.photo) ? (
                <img src={resolvePhotoUrl(selected.photo)!} alt={selected.name} className="w-full h-full object-cover"
                     onError={(e) => { e.currentTarget.style.display = 'none'; }} />
              ) : null}
              <span className="font-bold text-sm text-blue-600">{selected.name?.charAt(0)?.toUpperCase() || 'U'}</span>
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-bold text-blue-700 uppercase tracking-wide">Target Person</div>
              <div className="text-sm font-bold text-slate-900 truncate">{selected.name}</div>
              <div className="text-xs text-slate-500 font-mono">{selected.person_code || selected.person_id}</div>
            </div>
            <span className="px-2 py-1 rounded bg-blue-600 text-white text-xs font-semibold flex items-center gap-1 shrink-0">
              <Check className="w-3.5 h-3.5" /> Ready
            </span>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-semibold text-slate-600 block mb-1">Category</label>
            <select value={category} onChange={e => setCategory(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary">
              {CATEGORIES.map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-600 block mb-1">Severity</label>
            <select value={severity} onChange={e => setSeverity(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary">
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
          </div>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">Reason (shown with alert)</label>
          <textarea value={reason} onChange={e => setReason(e.target.value)}
                    placeholder="Reason (e.g., Security violation, Unauthorized entry attempt)" rows={2}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary" />
        </div>

        {error && (
          <div className="rounded-lg p-3 text-xs bg-danger/10 text-danger border border-danger/20">{error}</div>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button onClick={onClose} type="button"
                  className="px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm font-medium text-slate-700 transition-colors cursor-pointer">
            Cancel
          </button>
          <button onClick={submit} disabled={busy}
                  className="px-5 py-2 rounded-lg bg-danger text-sm font-semibold text-white hover:bg-danger/90 disabled:opacity-50 transition-colors shadow-sm shadow-danger/20 flex items-center gap-2 cursor-pointer">
            {busy ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> Adding…
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" /> Add to Watchlist
              </>
            )}
          </button>
        </div>
      </motion.div>
    </div>
  )
}

export default FaceWatchlist
