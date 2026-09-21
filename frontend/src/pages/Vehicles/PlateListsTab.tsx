import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertOctagon, Ban, Camera, CheckCircle2, Clock, Plus, Search, ShieldCheck,
  Trash2, X,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/utils'
import { api } from '@/api/api'

type Entry = {
  id: string
  plate_number: string
  list_type: string
  priority: number
  reason?: string
  notes?: string
  expiry?: number | null
  created_at?: string
}

type Hit = {
  id: string
  event_type: string
  plate_number?: string
  confidence?: number
  timestamp: number
  camera_id?: string
}

const BLACKLIST_TYPES = ['BLACKLIST', 'STOLEN', 'STOLEN VEHICLE', 'EXPIRED ACCESS', 'POLICE']
const WHITELIST_TYPES = ['WHITELIST', 'VIP', 'EMPLOYEE', 'CONTRACTOR', 'VISITOR']

const isBlack = (t?: string) => BLACKLIST_TYPES.includes((t || '').toUpperCase())

export default function PlateListsTab() {
  const [tab, setTab] = useState<'blacklist' | 'whitelist'>('blacklist')
  const [entries, setEntries] = useState<Entry[]>([])
  const [hits, setHits] = useState<Hit[]>([])
  const [search, setSearch] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [w, e] = await Promise.all([
        api.get('/api/plugins/anpr/watchlists', { params: { kind: tab } }),
        api.get('/api/plugins/anpr/events', { params: { limit: 100 } }),
      ])
      setEntries(w.data || [])
      setHits((e.data || []).filter((x: Hit) =>
        x.event_type === 'BLACKLIST_MATCH' || x.event_type === 'WHITELIST_MATCH'))
    } catch (err: any) {
      setError(err?.response?.data?.detail?.message || err?.message || 'Failed to load lists')
    }
  }, [tab])

  useEffect(() => {
    load()
    const t = setInterval(load, 20000)
    return () => clearInterval(t)
  }, [load])

  const remove = async (id: string) => {
    try {
      await api.delete(`/api/plugins/anpr/watchlists/${id}`)
      load()
    } catch (err: any) {
      setError(err?.response?.status === 403
        ? 'Your role cannot change the plate lists.'
        : 'Could not remove that entry.')
    }
  }

  const shown = useMemo(() => {
    if (!search.trim()) return entries
    const q = search.toUpperCase().replace(/[^A-Z0-9]/g, '')
    return entries.filter(e => e.plate_number.includes(q))
  }, [entries, search])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-primary" /> Plate Lists
          </h1>
          <p className="text-sm text-muted-foreground">
            Blacklisted and authorised vehicles, matched against every plate read
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg bg-background/60 border border-foreground/10 p-1">
            <button onClick={() => setTab('blacklist')}
                    className={cn('px-3 py-1.5 rounded text-sm font-medium transition-colors flex items-center gap-1.5',
                      tab === 'blacklist' ? 'bg-danger/20 text-danger' : 'text-muted-foreground')}>
              <Ban className="w-4 h-4" /> Blacklist
            </button>
            <button onClick={() => setTab('whitelist')}
                    className={cn('px-3 py-1.5 rounded text-sm font-medium transition-colors flex items-center gap-1.5',
                      tab === 'whitelist' ? 'bg-success/20 text-success' : 'text-muted-foreground')}>
              <CheckCircle2 className="w-4 h-4" /> Whitelist
            </button>
          </div>
          <button onClick={() => setAddOpen(true)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/20 text-primary text-sm font-medium hover:bg-primary/30 transition-colors">
            <Plus className="w-4 h-4" /> Add plate
          </button>
        </div>
      </div>

      {error && (
        <div className="glass border border-danger/40 bg-danger/10 rounded-xl p-4 text-sm text-danger">
          {error}
        </div>
      )}

      <PlateTester />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="glass border border-foreground/10 rounded-xl overflow-hidden">
          <div className="p-4 border-b border-foreground/10 flex items-center gap-3">
            <Search className="w-4 h-4 text-muted-foreground" />
            <input value={search} onChange={e => setSearch(e.target.value)}
                   placeholder={`Search the ${tab}`}
                   className="bg-transparent outline-none text-sm text-white flex-1" />
            <span className="text-xs text-muted-foreground">{shown.length}</span>
          </div>
          <div className="divide-y divide-white/5 max-h-[520px] overflow-y-auto">
            {shown.map(e => (
              <div key={e.id} className="p-4 flex items-center gap-4 hover:bg-foreground/5 group">
                <div className={cn('px-3 py-2 rounded-lg font-mono font-bold tracking-wider',
                  isBlack(e.list_type) ? 'bg-danger/15 text-danger' : 'bg-success/15 text-success')}>
                  {e.plate_number}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">
                    {e.list_type}{e.priority ? ` · priority ${e.priority}` : ''}
                  </div>
                  <div className="text-sm text-white truncate">
                    {e.reason || 'No reason recorded'}
                  </div>
                  {e.expiry ? (
                    <div className="text-[11px] text-muted-foreground mt-0.5">
                      Expires {new Date(e.expiry * 1000).toLocaleString()}
                    </div>
                  ) : null}
                </div>
                <button onClick={() => remove(e.id)} title="Remove"
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-2 rounded-lg hover:bg-danger/20 text-danger">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
            {shown.length === 0 && (
              <div className="p-12 text-center text-muted-foreground text-sm">
                Nothing on the {tab}.
              </div>
            )}
          </div>
        </div>

        <div className="glass border border-foreground/10 rounded-xl overflow-hidden">
          <div className="p-4 border-b border-foreground/10 flex items-center gap-2">
            <AlertOctagon className="w-4 h-4 text-danger" />
            <h3 className="text-sm font-semibold text-white">Recent list hits</h3>
            <span className="ml-auto text-xs text-muted-foreground">{hits.length}</span>
          </div>
          <div className="divide-y divide-white/5 max-h-[520px] overflow-y-auto">
            {hits.map(h => (
              <div key={h.id} className="p-4 flex items-center gap-4 hover:bg-foreground/5">
                <div className={cn('px-3 py-2 rounded-lg font-mono font-bold',
                  h.event_type === 'BLACKLIST_MATCH'
                    ? 'bg-danger/15 text-danger' : 'bg-success/15 text-success')}>
                  {h.plate_number || '—'}
                </div>
                <div className="min-w-0 flex-1">
                  <div className={cn('text-sm font-medium',
                    h.event_type === 'BLACKLIST_MATCH' ? 'text-danger' : 'text-success')}>
                    {h.event_type === 'BLACKLIST_MATCH' ? 'Blacklisted vehicle' : 'Authorised vehicle'}
                  </div>
                  <div className="text-xs text-muted-foreground flex items-center gap-3 mt-0.5">
                    <span className="flex items-center gap-1">
                      <Camera className="w-3 h-3" />{h.camera_id?.slice(0, 8) || '—'}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date((h.timestamp || 0) * 1000).toLocaleString()}
                    </span>
                  </div>
                </div>
                {h.confidence != null && (
                  <span className="text-xs font-mono text-muted-foreground">
                    {(h.confidence * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            ))}
            {hits.length === 0 && (
              <div className="p-12 text-center text-muted-foreground text-sm">
                No list hits recorded yet.
              </div>
            )}
          </div>
        </div>
      </div>

      {addOpen && <AddPlateDialog kind={tab} onClose={() => { setAddOpen(false); load() }} />}
    </div>
  )
}

/**
 * Shows exactly what a given read would match, and how. The distinction
 * matters: an exact hit and a hit reconstructed through OCR confusions call
 * for different amounts of trust from the operator acting on it.
 */
function PlateTester() {
  const [plate, setPlate] = useState('')
  const [result, setResult] = useState<any>(null)
  const [busy, setBusy] = useState(false)

  const run = async () => {
    if (!plate.trim()) return
    setBusy(true)
    try {
      const res = await api.get('/api/plugins/anpr/watchlists/check', { params: { plate } })
      setResult(res.data)
    } catch {
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  const kindLabel: Record<string, string> = {
    exact: 'exact match',
    ocr_equivalent: 'matched after allowing for OCR character confusions',
    fuzzy: 'matched with one further character difference',
  }

  return (
    <div className="glass border border-foreground/10 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-white mb-3">Test a plate against the lists</h3>
      <div className="flex flex-wrap gap-2">
        <input value={plate} onChange={e => setPlate(e.target.value)}
               onKeyDown={e => e.key === 'Enter' && run()}
               placeholder="e.g. UP16B3895"
               className="flex-1 min-w-[200px] bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white font-mono" />
        <button onClick={run} disabled={busy}
                className="px-4 py-2 rounded-lg bg-foreground/10 text-sm text-white disabled:opacity-40">
          {busy ? 'Checking…' : 'Check'}
        </button>
      </div>
      {result && (
        <div className={cn('mt-3 rounded-lg p-3 text-sm',
          !result.matched ? 'bg-foreground/5 text-muted-foreground'
            : result.is_blacklist ? 'bg-danger/10 text-danger' : 'bg-success/10 text-success')}>
          {!result.matched ? (
            <>
              <span className="font-mono">{result.normalised}</span> is not on any list
              <span className="text-xs block mt-1">
                {result.list_size} plate(s) currently listed
              </span>
            </>
          ) : (
            <>
              <span className="font-mono font-bold">{result.normalised}</span>
              {' → '}
              <span className="font-mono font-bold">{result.entry?.plate_number}</span>
              {' '}[{result.entry?.list_type}]
              <span className="text-xs block mt-1 opacity-80">
                {kindLabel[result.match_kind] || result.match_kind}
                {result.entry?.reason ? ` · ${result.entry.reason}` : ''}
              </span>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function AddPlateDialog({ kind, onClose }: { kind: 'blacklist' | 'whitelist'; onClose: () => void }) {
  const types = kind === 'blacklist' ? BLACKLIST_TYPES : WHITELIST_TYPES
  const [form, setForm] = useState({
    plate_number: '', list_type: types[0], priority: 0, reason: '', notes: '',
  })
  const [expiry, setExpiry] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!form.plate_number.trim()) {
      setError('A plate number is required.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.post('/api/plugins/anpr/watchlists', {
        ...form,
        priority: Number(form.priority) || 0,
        reason: form.reason || null,
        notes: form.notes || null,
        expiry: expiry ? new Date(expiry).getTime() / 1000 : null,
      })
      onClose()
    } catch (e: any) {
      const d = e?.response?.data?.detail
      setError(e?.response?.status === 403
        ? 'Your role cannot change the plate lists.'
        : (typeof d === 'string' ? d : d?.message) || 'Could not add that plate.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
         onClick={onClose}>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                  onClick={e => e.stopPropagation()}
                  className="glass border border-foreground/10 rounded-2xl p-6 w-full max-w-md space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            {kind === 'blacklist'
              ? <Ban className="w-5 h-5 text-danger" />
              : <CheckCircle2 className="w-5 h-5 text-success" />}
            Add to {kind}
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <input value={form.plate_number}
               onChange={e => setForm({ ...form, plate_number: e.target.value.toUpperCase() })}
               placeholder="Plate number"
               className="w-full bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white font-mono tracking-wider" />
        <p className="text-[11px] text-muted-foreground -mt-2">
          Spaces and dashes are ignored; the plate is stored normalised.
        </p>

        <div className="grid grid-cols-2 gap-2">
          <select value={form.list_type}
                  onChange={e => setForm({ ...form, list_type: e.target.value })}
                  className="bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white">
            {types.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <input type="number" min={0} max={10} value={form.priority}
                 onChange={e => setForm({ ...form, priority: Number(e.target.value) })}
                 placeholder="Priority"
                 className="bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white" />
        </div>

        <input value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })}
               placeholder="Reason (shown with every alert)"
               className="w-full bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white" />

        <div>
          <label className="text-xs text-muted-foreground">Expires (optional)</label>
          <input type="datetime-local" value={expiry} onChange={e => setExpiry(e.target.value)}
                 className="w-full mt-1 bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white" />
        </div>

        {kind === 'whitelist' && (
          <div className="rounded-lg p-3 text-xs bg-info/10 text-info">
            A whitelist entry only authorises on an exact plate read. Approximate
            reads are ignored here on purpose, so a misread never opens a barrier
            for the wrong vehicle.
          </div>
        )}

        {error && <div className="rounded-lg p-3 text-xs bg-danger/10 text-danger">{error}</div>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose}
                  className="px-4 py-2 rounded-lg bg-foreground/10 text-sm text-white">
            Cancel
          </button>
          <button onClick={submit} disabled={busy}
                  className={cn('px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-40',
                    kind === 'blacklist' ? 'bg-danger' : 'bg-success')}>
            {busy ? 'Adding…' : 'Add'}
          </button>
        </div>
      </motion.div>
    </div>
  )
}

