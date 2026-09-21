import React, { useState } from 'react'
import {
  Key,
  Copy,
  Check,
  Calendar,
  Clock,
  ShieldCheck,
  RotateCcw,
  Plus,
  Search,
  AlertCircle
} from 'lucide-react'
import { cn } from '@/utils/utils'

interface LicenseEngineTabProps {
  customers: any[]
  onExtendLicense: (customerId: string, duration: string) => Promise<void>
}

export function LicenseEngineTab({ customers, onExtendLicense }: LicenseEngineTabProps) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')

  const handleCopy = (key: string) => {
    navigator.clipboard.writeText(key)
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(null), 2500)
  }

  const getDaysLeft = (expiryDateStr: string) => {
    try {
      const exp = new Date(expiryDateStr)
      const now = new Date()
      const diffTime = exp.getTime() - now.getTime()
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
      return diffDays
    } catch {
      return 0
    }
  }

  const filtered = customers.filter(
    (c) =>
      c.companyName?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.licenseKey?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="space-y-6">
      {/* Header Info */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-bold text-foreground flex items-center gap-2">
            <Key className="w-5 h-5 text-amber-400" /> Enterprise License Key Registry
          </h3>
          <p className="text-xs text-muted-foreground">
            Manage cryptographic license keys, validity periods, and client subscription lifecycles.
          </p>
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search license or client..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-card border border-border rounded-xl pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {/* Licenses Table */}
      <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-lg">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/20 border-b border-border text-xs uppercase font-bold text-muted-foreground">
              <tr>
                <th className="py-3.5 px-4">Client Organization</th>
                <th className="py-3.5 px-4">License Key</th>
                <th className="py-3.5 px-4">Plan / Duration</th>
                <th className="py-3.5 px-4">Expiry Date</th>
                <th className="py-3.5 px-4">Days Left</th>
                <th className="py-3.5 px-4">Status</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {filtered.map((cust) => {
                const daysLeft = getDaysLeft(cust.expiryDate)
                const isExpiring = daysLeft <= 15
                const isExpired = daysLeft <= 0

                return (
                  <tr key={cust.id} className="hover:bg-muted/10 transition-colors">
                    <td className="py-4 px-4">
                      <div className="font-bold text-foreground">{cust.companyName}</div>
                      <div className="text-xs text-muted-foreground">{cust.siteLocation}</div>
                    </td>

                    <td className="py-4 px-4 font-mono">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-primary tracking-wider">{cust.licenseKey}</span>
                        <button
                          onClick={() => handleCopy(cust.licenseKey)}
                          className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                          title="Copy License Key"
                        >
                          {copiedKey === cust.licenseKey ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </td>

                    <td className="py-4 px-4 text-xs">
                      <span className="font-semibold text-foreground">{cust.duration}</span>
                      <div className="text-muted-foreground">{cust.enabledServices?.length || 0} AI Modules</div>
                    </td>

                    <td className="py-4 px-4 font-mono text-xs text-foreground/90">
                      {cust.expiryDate}
                    </td>

                    <td className="py-4 px-4">
                      <span
                        className={cn(
                          'text-xs font-bold font-mono px-2.5 py-1 rounded-full',
                          isExpired
                            ? 'bg-danger/20 text-danger'
                            : isExpiring
                            ? 'bg-amber-500/20 text-amber-400 animate-pulse'
                            : 'bg-emerald-500/15 text-emerald-400'
                        )}
                      >
                        {isExpired ? 'Expired' : `${daysLeft} Days`}
                      </span>
                    </td>

                    <td className="py-4 px-4">
                      <span
                        className={cn(
                          'text-[10px] font-bold px-2 py-0.5 rounded-full',
                          cust.status === 'Active'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-amber-500/20 text-amber-400'
                        )}
                      >
                        {cust.status}
                      </span>
                    </td>

                    <td className="py-4 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => onExtendLicense(cust.id, '1 Month')}
                          className="px-2.5 py-1 rounded-lg bg-muted/20 hover:bg-primary/20 text-xs font-semibold text-muted-foreground hover:text-primary transition-colors border border-border/50"
                          title="Extend 1 Month"
                        >
                          +1 Month
                        </button>
                        <button
                          onClick={() => onExtendLicense(cust.id, '1 Year')}
                          className="px-2.5 py-1 rounded-lg bg-primary/15 hover:bg-primary/30 text-xs font-semibold text-primary transition-colors border border-primary/30"
                          title="Extend 1 Year"
                        >
                          +1 Year
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
