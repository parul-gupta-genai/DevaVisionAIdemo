import React, { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Camera } from 'lucide-react'
import { cn } from '@/utils/utils'
import { api } from '@/api/api'

export default function ViolationsTab() {
  const [violations, setViolations] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const viol = await api.get('/api/ppe/violations', { params: { limit: 50 } })
      setViolations(viol.data?.items || [])
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message || e?.message || 'Failed to load violations')
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="glass border border-foreground/10 rounded-xl overflow-hidden mt-6">
      <div className="p-4 border-b border-foreground/10 flex items-center gap-2">
        <AlertTriangle className="w-5 h-5 text-warning" />
        <h3 className="text-lg font-bold text-white">Recent Violations</h3>
        <span className="ml-auto text-xs text-muted-foreground bg-foreground/10 px-2 py-1 rounded-full">{violations.length} total</span>
      </div>
      
      {error && <div className="p-4 text-sm text-danger bg-danger/10">{error}</div>}

      <div className="divide-y divide-white/5 max-h-[600px] overflow-y-auto">
        {violations.map(v => (
          <div key={v.violation_id} className="p-4 flex items-center gap-4 hover:bg-foreground/5 transition-colors">
            {v.snapshot_file ? (
              <img src={v.snapshot_file} alt="" className="w-16 h-16 rounded-lg object-cover border border-warning/30 shadow-md" />
            ) : (
              <div className="w-16 h-16 rounded-lg bg-foreground/5 border border-foreground/10 flex items-center justify-center">
                <Camera className="w-5 h-5 text-foreground/30" />
              </div>
            )}
            <div className="min-w-0 flex-1">
              <div className="text-base font-bold text-white">
                {v.violation_type.replace(/_/g, ' ')}
                {v.vendor_name ? <span className="text-muted-foreground font-normal"> · {v.vendor_name}</span> : ''}
              </div>
              <div className="text-sm text-muted-foreground flex items-center gap-2 mt-1">
                <Camera className="w-3 h-3" />
                {v.camera_id?.slice(0, 8) || '—'} · {new Date(v.timestamp).toLocaleString()}
              </div>
            </div>
            <span className={cn('px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider',
              v.severity === 'critical' ? 'bg-danger/20 text-danger border border-danger/30'
                : 'bg-warning/20 text-warning border border-warning/30')}>
              {v.severity || 'warning'}
            </span>
          </div>
        ))}
        {violations.length === 0 && !error && (
          <div className="p-12 text-center flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-success/10 flex items-center justify-center">
              <AlertTriangle className="w-6 h-6 text-success" />
            </div>
            <div>
              <div className="text-sm font-bold text-white">No violations recorded.</div>
              <div className="text-xs text-muted-foreground mt-1">Your site is currently 100% compliant.</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
