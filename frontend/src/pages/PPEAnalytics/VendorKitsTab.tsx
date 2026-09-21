import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Camera, Crosshair, Palette, Plus, Shirt, Trash2, X, HardHat } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/utils'
import { api } from '@/api/api'

const REGION_ICON: Record<string, any> = { HEAD: HardHat, TORSO: Shirt }

export default function VendorKitsTab() {
  const [colours, setColours] = useState<any[]>([])
  const [vendors, setVendors] = useState<any[]>([])
  const [cameras, setCameras] = useState<any[]>([])
  const [meta, setMeta] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [calibrateOpen, setCalibrateOpen] = useState(false)
  const [vendorOpen, setVendorOpen] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [c, v, cam, m] = await Promise.all([
        api.get('/api/ppe/colours'),
        api.get('/api/ppe/vendors'),
        api.get('/api/ppe/cameras'),
        api.get('/api/ppe/meta'),
      ])
      setColours(c.data || [])
      setVendors(v.data || [])
      setCameras(cam.data || [])
      setMeta(m.data)
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message || e?.message || 'Failed to load')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const removeColour = async (id: string) => {
    try {
      await api.delete(`/api/ppe/colours/${id}`)
      load()
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message || 'Could not delete that colour.')
    }
  }

  const removeVendor = async (id: string) => {
    try {
      await api.delete(`/api/ppe/vendors/${id}`)
      load()
    } catch (e: any) {
      setError(e?.response?.status === 403 ? 'Your role cannot configure PPE kits.' : 'Could not delete that vendor.')
    }
  }

  const removeKitItem = async (id: string) => {
    try {
      await api.delete(`/api/ppe/kit/${id}`)
      load()
    } catch {
      setError('Could not remove that kit item.')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide">PPE Vendor Colour Kits</h2>
          <p className="text-sm text-muted-foreground">Identify which agency a worker belongs to from their helmet and vest colours</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setCalibrateOpen(true)} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-foreground/10 text-white text-sm font-medium hover:bg-foreground/20 transition-colors">
            <Crosshair className="w-4 h-4" /> Calibrate a colour
          </button>
          <button onClick={() => setVendorOpen(true)} disabled={colours.length === 0} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/20 text-primary text-sm font-medium hover:bg-primary/30 transition-colors disabled:opacity-40">
            <Plus className="w-4 h-4" /> Add vendor
          </button>
        </div>
      </div>

      {error && <div className="glass border border-danger/40 bg-danger/10 rounded-xl p-4 text-sm text-danger">{error}</div>}
      
      {meta && !meta.catalogue_configured && (
        <div className="glass border border-info/40 bg-info/10 rounded-xl p-4 text-sm text-info">
          No vendor kits are defined yet, so PPE detection is running in its original two-colour mode (blue = Contractor 1, yellow = Contractor 2). Calibrate the colours your vendors actually wear, then define a vendor, and identification switches over automatically.
        </div>
      )}

      {/* Colours */}
      <div className="glass border border-foreground/10 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Palette className="w-4 h-4 text-primary" /> Calibrated colours
          <span className="text-xs text-muted-foreground font-normal">({colours.length})</span>
        </h3>
        {colours.length === 0 ? (
          <p className="text-sm text-muted-foreground">None yet. Calibrate from a photo of the garment, or from a live camera.</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {colours.map(c => (
              <div key={c.colour_id} className="group flex items-center gap-3 bg-background/40 rounded-lg pl-2 pr-3 py-2 border border-foreground/10">
                <span className="w-8 h-8 rounded-md border border-white/20 shrink-0" style={{ background: c.display_hex || '#666' }} />
                <div>
                  <div className="text-sm text-white font-medium">{c.name}</div>
                  <div className="text-[11px] text-muted-foreground">
                    {c.hsv_ranges?.length || 0} range{(c.hsv_ranges?.length || 0) === 1 ? '' : 's'}
                    {c.wraps_hue && ' · wraps hue'}
                    {c.in_use_by ? ` · used ${c.in_use_by}x` : ' · unused'}
                  </div>
                </div>
                <button onClick={() => removeColour(c.colour_id)} className="opacity-0 group-hover:opacity-100 transition-opacity text-danger p-1"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Vendors */}
        <div className="glass border border-foreground/10 rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-white">Vendor kits ({vendors.length})</h3>
          {vendors.length === 0 && (
            <p className="text-sm text-muted-foreground">No vendors defined. A vendor is a set of colours in body regions — for example a yellow helmet with an orange vest.</p>
          )}
          {vendors.map(v => (
            <div key={v.vendor_id} className="rounded-lg border border-foreground/10 bg-background/40 p-4 group">
              <div className="flex items-center gap-3 mb-3">
                <span className="w-3 h-3 rounded-full shrink-0" style={{ background: v.display_hex || '#22c55e' }} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-white truncate">{v.name}</div>
                  {v.code && <div className="text-[11px] text-muted-foreground">{v.code}</div>}
                </div>
                <button onClick={() => removeVendor(v.vendor_id)} className="opacity-0 group-hover:opacity-100 transition-opacity text-danger p-1"><Trash2 className="w-4 h-4" /></button>
              </div>
              <div className="flex flex-wrap gap-2">
                {v.kit_items.map((item: any) => {
                  const Icon = REGION_ICON[item.body_region] || Shirt
                  const swatch = colours.find(c => c.colour_id === item.colour_id)
                  return (
                    <span key={item.item_id} className="group/i inline-flex items-center gap-2 text-xs bg-foreground/5 rounded-lg px-2 py-1.5">
                      <Icon className="w-3.5 h-3.5 text-muted-foreground" />
                      <span className="w-3 h-3 rounded-sm border border-white/20" style={{ background: swatch?.display_hex || '#666' }} />
                      <span className="text-white">{item.item_type.toLowerCase()}</span>
                      <span className="text-muted-foreground">{item.colour_name || swatch?.name} {!item.is_required && '(optional)'}</span>
                      <button onClick={() => removeKitItem(item.item_id)} className="opacity-0 group-hover/i:opacity-100 text-danger"><X className="w-3 h-3" /></button>
                    </span>
                  )
                })}
                {v.kit_items.length === 0 && <span className="text-xs text-warning">No kit items — this vendor cannot be identified.</span>}
                <AddKitButton vendorId={v.vendor_id} colours={colours} regions={Object.keys(meta?.body_regions || {})} itemTypes={meta?.item_types || []} onDone={load} />
              </div>
            </div>
          ))}
        </div>

        {/* Camera Enforcement */}
        <div className="glass border border-foreground/10 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-white mb-3">Camera enforcement</h3>
          {cameras.length === 0 ? (
            <p className="text-sm text-muted-foreground">No cameras configured. Without a configuration a camera accepts any catalogued vendor and alerts only on nobody being recognisable.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Camera</th>
                    <th className="py-2 pr-4 font-medium">Expected vendors</th>
                    <th className="py-2 pr-4 font-medium">Alerts on</th>
                    <th className="py-2 pr-4 font-medium">Severity</th>
                    <th className="py-2 font-medium">Enforcing</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {cameras.map(c => (
                    <tr key={c.camera_id}>
                      <td className="py-2 pr-4 font-mono text-xs text-white">{c.camera_id.slice(0, 8)}</td>
                      <td className="py-2 pr-4 text-muted-foreground">{c.expected_vendor_names?.join(', ') || 'any'}</td>
                      <td className="py-2 pr-4 text-muted-foreground">{c.alert_on?.map((a: string) => a.replace(/_/g, ' ')).join(', ') || '—'}</td>
                      <td className="py-2 pr-4 text-muted-foreground">{c.severity}</td>
                      <td className="py-2">
                        <span className={cn('px-2 py-0.5 rounded text-[10px] font-bold', c.enforce ? 'bg-success/20 text-success' : 'bg-foreground/10 text-muted-foreground')}>
                          {c.enforce ? 'YES' : 'NO'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {calibrateOpen && <CalibrateDialog onClose={() => { setCalibrateOpen(false); load() }} />}
      {vendorOpen && <VendorDialog colours={colours} meta={meta} onClose={() => { setVendorOpen(false); load() }} />}
    </div>
  )
}

function CalibrateDialog({ onClose }: { onClose: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<'upload' | 'camera'>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [cameraId, setCameraId] = useState('')
  const [region, setRegion] = useState('TORSO')
  const [result, setResult] = useState<any>(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      let res
      if (mode === 'upload') {
        if (!file) { setError('Choose a photo first.'); return }
        const fd = new FormData()
        fd.append('file', file)
        res = await api.post('/api/ppe/calibrate/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      } else {
        if (!cameraId.trim()) { setError('Enter a camera id.'); return }
        res = await api.post('/api/ppe/calibrate/camera', null, { params: { camera_id: cameraId.trim(), region } })
      }
      setResult(res.data)
      if (!res.data.ok) setError(res.data.message)
    } catch (e: any) {
      const d = e?.response?.data?.detail
      setError((typeof d === 'string' ? d : d?.message) || 'Calibration failed.')
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (!result?.hsv_ranges || !name.trim()) { setError('Give the colour a name.'); return }
    setBusy(true)
    try {
      await api.post('/api/ppe/colours', { name: name.trim(), hsv_ranges: result.hsv_ranges, display_hex: result.display_hex, calibrated_on_camera: mode === 'camera' ? cameraId.trim() : null })
      onClose()
    } catch (e: any) {
      const d = e?.response?.data?.detail
      setError((typeof d === 'string' ? d : d?.message) || 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} onClick={e => e.stopPropagation()} className="glass border border-foreground/10 rounded-2xl p-6 w-full max-w-lg space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-white flex items-center gap-2"><Crosshair className="w-5 h-5 text-primary" /> Calibrate a colour</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-white"><X className="w-5 h-5" /></button>
        </div>
        <p className="text-xs text-muted-foreground">Colours are derived from pixels this site's cameras actually produce.</p>
        <div className="flex rounded-lg bg-background/60 border border-foreground/10 p-1">
          {(['upload', 'camera'] as const).map(m => (
            <button key={m} onClick={() => { setMode(m); setResult(null) }} className={cn('flex-1 px-3 py-1.5 rounded text-sm font-medium transition-colors', mode === m ? 'bg-primary/20 text-primary' : 'text-muted-foreground')}>{m === 'upload' ? 'From a photo' : 'From a live camera'}</button>
          ))}
        </div>
        {mode === 'upload' ? (
          <div className="flex gap-4">
            <div onClick={() => fileRef.current?.click()} className="w-28 h-28 shrink-0 rounded-xl border border-dashed border-foreground/20 bg-background/40 flex items-center justify-center cursor-pointer overflow-hidden">
              {preview ? <img src={preview} alt="" className="w-full h-full object-cover" /> : <span className="text-xs text-muted-foreground text-center px-2">Photo of the garment</span>}
            </div>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={e => { const f = e.target.files?.[0] || null; setFile(f); setResult(null); setPreview(f ? URL.createObjectURL(f) : null) }} />
            <p className="text-xs text-muted-foreground flex-1">Fill the frame with the garment. Shadow, glare and background all widen the range and make it match things it should not.</p>
          </div>
        ) : (
          <div className="space-y-2">
            <input value={cameraId} onChange={e => setCameraId(e.target.value)} placeholder="Camera id" className="w-full bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white font-mono" />
            <select value={region} onChange={e => setRegion(e.target.value)} className="w-full bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white">
              <option value="HEAD">Head (helmet)</option><option value="TORSO">Torso (vest / jacket)</option><option value="LEGS">Legs</option>
            </select>
          </div>
        )}
        <button onClick={run} disabled={busy} className="w-full px-4 py-2 rounded-lg bg-foreground/10 text-sm text-white disabled:opacity-40">{busy ? 'Sampling…' : 'Sample the colour'}</button>
        {result?.ok && (
          <div className="rounded-lg p-3 bg-background/40 space-y-2">
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Name this colour, e.g. 'Acme hi-vis orange'" className="w-full bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white" />
          </div>
        )}
        {error && <div className="rounded-lg p-3 text-xs bg-danger/10 text-danger">{error}</div>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg bg-foreground/10 text-sm text-white">Cancel</button>
          <button onClick={save} disabled={busy || !result?.ok} className="px-4 py-2 rounded-lg bg-primary text-sm font-medium text-white disabled:opacity-40">Save colour</button>
        </div>
      </motion.div>
    </div>
  )
}

function AddKitButton({ vendorId, colours, regions, itemTypes, onDone }: any) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ colour_id: '', item_type: 'VEST', body_region: 'TORSO', is_required: true, min_coverage: 0.12 })
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    if (!form.colour_id) { setError('Pick a colour.'); return }
    try {
      await api.post(`/api/ppe/vendors/${vendorId}/kit`, form)
      setOpen(false); onDone()
    } catch (e: any) {
      const d = e?.response?.data?.detail
      setError((typeof d === 'string' ? d : d?.message) || 'Could not add.')
    }
  }

  if (!open) return <button onClick={() => setOpen(true)} className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg border border-dashed border-foreground/20 text-muted-foreground hover:text-white"><Plus className="w-3 h-3" /> item</button>
  return (
    <div className="w-full mt-2 rounded-lg border border-foreground/10 bg-background/60 p-3 space-y-2">
      <div className="grid grid-cols-3 gap-2">
        <select value={form.colour_id} onChange={e => setForm({ ...form, colour_id: e.target.value })} className="bg-background/60 border border-foreground/10 rounded px-2 py-1.5 text-xs text-white">
          <option value="">Colour…</option>{colours.map((c: any) => <option key={c.colour_id} value={c.colour_id}>{c.name}</option>)}
        </select>
        <select value={form.item_type} onChange={e => setForm({ ...form, item_type: e.target.value })} className="bg-background/60 border border-foreground/10 rounded px-2 py-1.5 text-xs text-white">
          {(itemTypes.length ? itemTypes : ['HELMET', 'VEST']).map((t: any) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={form.body_region} onChange={e => setForm({ ...form, body_region: e.target.value })} className="bg-background/60 border border-foreground/10 rounded px-2 py-1.5 text-xs text-white">
          {(regions.length ? regions : ['HEAD', 'TORSO']).map((r: any) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <input type="checkbox" checked={form.is_required} onChange={e => setForm({ ...form, is_required: e.target.checked })} /> Required
      </label>
      {error && <div className="text-xs text-danger">{error}</div>}
      <div className="flex justify-end gap-2">
        <button onClick={() => setOpen(false)} className="px-3 py-1.5 rounded bg-foreground/10 text-xs text-white">Cancel</button>
        <button onClick={submit} className="px-3 py-1.5 rounded bg-primary text-xs text-white">Add</button>
      </div>
    </div>
  )
}

function VendorDialog({ colours, meta, onClose }: any) {
  const [form, setForm] = useState({ name: '', code: '', display_hex: '#22c55e' })
  const [helmet, setHelmet] = useState('')
  const [vest, setVest] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!form.name.trim()) { setError('The vendor needs a name.'); return }
    const kit_items: any[] = []
    if (helmet) kit_items.push({ colour_id: helmet, item_type: 'HELMET', body_region: 'HEAD', is_required: true, min_coverage: 0.10 })
    if (vest) kit_items.push({ colour_id: vest, item_type: 'VEST', body_region: 'TORSO', is_required: true, min_coverage: 0.12 })
    if (!kit_items.length) { setError('Pick at least one garment colour.'); return }
    setBusy(true)
    try {
      await api.post('/api/ppe/vendors', { ...form, kit_items })
      onClose()
    } catch (e: any) {
      const d = e?.response?.data?.detail
      setError((typeof d === 'string' ? d : d?.message) || 'Could not create vendor.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} onClick={e => e.stopPropagation()} className="glass border border-foreground/10 rounded-2xl p-6 w-full max-w-md space-y-4">
        <h3 className="text-lg font-bold text-white">Add a vendor</h3>
        <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Vendor / agency name" className="w-full bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white" />
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-muted-foreground">Helmet colour</label>
            <select value={helmet} onChange={e => setHelmet(e.target.value)} className="w-full mt-1 bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white">
              <option value="">None</option>{colours.map((c: any) => <option key={c.colour_id} value={c.colour_id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Vest colour</label>
            <select value={vest} onChange={e => setVest(e.target.value)} className="w-full mt-1 bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white">
              <option value="">None</option>{colours.map((c: any) => <option key={c.colour_id} value={c.colour_id}>{c.name}</option>)}
            </select>
          </div>
        </div>
        {error && <div className="rounded-lg p-3 text-xs bg-danger/10 text-danger">{error}</div>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg bg-foreground/10 text-sm text-white">Cancel</button>
          <button onClick={submit} disabled={busy} className="px-4 py-2 rounded-lg bg-primary text-sm font-medium text-white disabled:opacity-40">{busy ? 'Saving…' : 'Create'}</button>
        </div>
      </motion.div>
    </div>
  )
}
