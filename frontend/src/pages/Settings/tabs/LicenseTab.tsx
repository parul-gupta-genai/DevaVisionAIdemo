import React, { useState, useEffect } from 'react'
import {
  ShieldCheck,
  Key,
  Calendar,
  Video,
  CheckCircle2,
  CreditCard,
  Sparkles,
  RefreshCw,
  Clock,
  ArrowUpRight,
  X
} from 'lucide-react'
import { api } from '@/api/api'
import { useToastStore } from '@/store/useToastStore'
import { cn } from '@/utils/utils'

export function LicenseTab() {
  const [license, setLicense] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRenewOpen, setIsRenewOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const addToast = useToastStore((s) => s.addToast)

  const [paymentForm, setPaymentForm] = useState({
    amount: 14490,
    durationMonths: 12,
    paymentMethod: 'UPI / Direct NetBanking',
  })

  const loadLicense = async () => {
    setIsLoading(true)
    try {
      const res = await api.get('/api/customer/license')
      setLicense(res.data)
    } catch (err) {
      console.error('Failed to load customer license:', err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadLicense()
  }, [])

  const handleRenewPayment = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    try {
      await api.post('/api/customer/pay-renew', {
        customerId: license?.customerId || 'cust_101',
        amount: paymentForm.amount,
        plan: `Enterprise AI Suite (${paymentForm.durationMonths} Months)`,
        paymentMethod: paymentForm.paymentMethod,
        durationMonths: paymentForm.durationMonths,
      })

      addToast({
        title: 'Payment Successful',
        message: `Subscription extended by ${paymentForm.durationMonths} months. Recorded in Provider Ledger.`,
        type: 'success',
      })
      setIsRenewOpen(false)
      await loadLicense()
    } catch (err: any) {
      addToast({
        title: 'Payment Error',
        message: err.message || 'Payment processing failed',
        type: 'danger',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading && !license) {
    return (
      <div className="p-8 flex items-center justify-center gap-3 text-muted-foreground">
        <RefreshCw className="w-5 h-5 animate-spin text-primary" /> Loading license information...
      </div>
    )
  }

  const daysRemaining = license?.daysRemaining ?? 365
  const isExpiring = daysRemaining <= 15
  const isExpired = daysRemaining <= 0

  return (
    <div className="relative z-10 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/20 border border-primary/40 flex items-center justify-center shadow-[0_0_15px_rgba(99,102,241,0.3)]">
            <ShieldCheck className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-wide">Subscription & AI License</h2>
            <p className="text-xs text-muted-foreground">
              Provisioned by your Solution Provider for {license?.companyName || 'Enterprise Site'}
            </p>
          </div>
        </div>

        <button
          onClick={() => setIsRenewOpen(true)}
          className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-black font-bold text-xs flex items-center gap-2 shadow-lg shadow-emerald-500/20 transition-all hover:scale-[1.02]"
        >
          <CreditCard className="w-4 h-4" /> Pay & Renew License
        </button>
      </div>

      {/* Main License Card */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 p-6 rounded-2xl bg-gradient-to-br from-primary/15 via-card to-card border border-primary/30 shadow-xl space-y-5 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-48 h-48 bg-primary/10 rounded-full blur-3xl pointer-events-none -mr-10 -mt-10" />

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 relative z-10">
            <div>
              <span className="text-[10px] uppercase font-bold text-primary tracking-widest block">
                Active Plan
              </span>
              <h3 className="text-2xl font-black text-white mt-0.5">{license?.planName || 'Enterprise AI Suite'}</h3>
              <p className="text-xs text-muted-foreground mt-0.5">{license?.companyName}</p>
            </div>

            <div
              className={cn(
                'px-4 py-2 rounded-xl border font-mono font-bold text-xs self-start sm:self-center',
                isExpired
                  ? 'bg-danger/20 border-danger/40 text-danger'
                  : isExpiring
                  ? 'bg-amber-500/20 border-amber-500/40 text-amber-400 animate-pulse'
                  : 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400'
              )}
            >
              {isExpired ? 'EXPIRED' : `${daysRemaining} DAYS REMAINING`}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 relative z-10">
            <div className="p-3 rounded-xl bg-background/50 border border-white/10">
              <span className="text-muted-foreground text-[10px] uppercase font-bold block">License Key</span>
              <code className="text-xs font-mono font-bold text-primary tracking-wider mt-1 block">
                {license?.licenseKey || 'DEVA-CORP-XXXX-XXXX'}
              </code>
            </div>

            <div className="p-3 rounded-xl bg-background/50 border border-white/10">
              <span className="text-muted-foreground text-[10px] uppercase font-bold block">Expiry Date</span>
              <span className="text-xs font-mono font-bold text-white mt-1 block">
                {license?.expiryDate || '2027-09-09'}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-background/50 border border-white/10">
              <span className="text-muted-foreground text-[10px] uppercase font-bold block">Camera Quota</span>
              <span className="text-xs font-bold text-purple-300 mt-1 flex items-center gap-1">
                <Video className="w-3.5 h-3.5" /> {license?.activeCameras || 4} / {license?.maxCameras || 16} Active
              </span>
            </div>
          </div>
        </div>

        {/* Quick Help Card */}
        <div className="p-6 rounded-2xl bg-card border border-border space-y-4 flex flex-col justify-between">
          <div>
            <span className="text-xs font-bold text-foreground uppercase tracking-wider block">Solution Provider Info</span>
            <p className="text-xs text-muted-foreground mt-2">
              Your software features, licenses, and AI capabilities are managed via your certified Solution Provider.
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-primary/10 border border-primary/20 text-xs text-primary space-y-1">
            <span className="font-bold block">Need more camera capacity or new AI models?</span>
            <p className="text-[11px] text-muted-foreground">Contact your provider to instantly unlock additional modules.</p>
          </div>
        </div>
      </div>

      {/* Provisioned Services List */}
      <div className="p-6 rounded-2xl bg-card border border-border shadow-md space-y-4">
        <h3 className="text-base font-bold text-foreground flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary" /> Licensed AI Modules & Capabilities
        </h3>
        <p className="text-xs text-muted-foreground">
          Features unlocked for your organization by your Solution Provider:
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-2">
          {(license?.availableServices || []).map((srv: any) => {
            const isUnlocked = (license?.enabledServices || []).includes(srv.id)
            return (
              <div
                key={srv.id}
                className={cn(
                  'p-4 rounded-xl border flex items-start justify-between gap-3 transition-all',
                  isUnlocked
                    ? 'border-emerald-500/30 bg-emerald-500/5'
                    : 'border-border/50 bg-muted/10 opacity-50'
                )}
              >
                <div className="flex items-start gap-2.5">
                  <span className="text-2xl">{srv.icon}</span>
                  <div>
                    <span className="font-bold text-xs text-foreground block">{srv.name}</span>
                    <span className="text-[10px] text-muted-foreground block mt-0.5">{srv.category}</span>
                  </div>
                </div>

                <span
                  className={cn(
                    'text-[10px] font-bold px-2 py-0.5 rounded-full shrink-0',
                    isUnlocked ? 'bg-emerald-500/20 text-emerald-400' : 'bg-muted text-muted-foreground'
                  )}
                >
                  {isUnlocked ? '✓ Licensed' : 'Locked'}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Self-Renewal Modal */}
      {isRenewOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl w-full max-w-md p-6 space-y-5 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="font-bold text-base text-foreground flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-emerald-400" /> Subscription Renewal
              </h3>
              <button onClick={() => setIsRenewOpen(false)} className="p-1 rounded-lg hover:bg-muted text-muted-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleRenewPayment} className="space-y-4">
              <div className="p-3.5 rounded-xl bg-primary/10 border border-primary/20 text-xs">
                <span className="text-muted-foreground block">Customer:</span>
                <span className="font-bold text-white block">{license?.companyName}</span>
                <span className="text-[10px] text-primary font-mono mt-0.5 block">Key: {license?.licenseKey}</span>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold uppercase text-foreground">Select Duration</label>
                <select
                  value={paymentForm.durationMonths}
                  onChange={(e) => {
                    const months = parseInt(e.target.value)
                    const base = license?.monthlyFee || 14490
                    setPaymentForm({
                      ...paymentForm,
                      durationMonths: months,
                      amount: base * (months === 12 ? 10 : months), // 2 months free on annual
                    })
                  }}
                  className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value={1}>1 Month (₹{(license?.monthlyFee || 14490).toLocaleString('en-IN')})</option>
                  <option value={3}>3 Months (₹{((license?.monthlyFee || 14490) * 3).toLocaleString('en-IN')})</option>
                  <option value={6}>6 Months (₹{((license?.monthlyFee || 14490) * 6).toLocaleString('en-IN')})</option>
                  <option value={12}>1 Year — Annual Savings (₹{((license?.monthlyFee || 14490) * 10).toLocaleString('en-IN')})</option>
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold uppercase text-foreground">Payment Method</label>
                <select
                  value={paymentForm.paymentMethod}
                  onChange={(e) => setPaymentForm({ ...paymentForm, paymentMethod: e.target.value })}
                  className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="UPI / QR Code / NetBanking">UPI / Instant QR Code</option>
                  <option value="Corporate Credit / Debit Card">Corporate Card</option>
                  <option value="Direct NEFT / RTGS Transfer">NEFT / RTGS Transfer</option>
                </select>
              </div>

              <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-between">
                <span className="text-xs font-bold text-muted-foreground uppercase">Total Amount</span>
                <span className="text-xl font-black text-emerald-400 font-mono">
                  ₹{paymentForm.amount.toLocaleString('en-IN')}
                </span>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsRenewOpen(false)}
                  className="px-4 py-2 rounded-xl border border-border hover:bg-muted text-sm text-muted-foreground"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-sm shadow-md disabled:opacity-50"
                >
                  {isSubmitting ? 'Processing...' : 'Confirm & Renew Plan'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
export default LicenseTab
