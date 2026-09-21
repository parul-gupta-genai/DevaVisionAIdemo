import React from 'react'
import {
  Users,
  ShieldCheck,
  CreditCard,
  Video,
  AlertTriangle,
  ArrowUpRight,
  Sparkles,
  CheckCircle2,
  Calendar,
  Layers
} from 'lucide-react'
import { cn } from '@/utils/utils'

interface OverviewTabProps {
  stats: any
  customers: any[]
  payments: any[]
  onNavigateTab: (tabId: string) => void
  onOpenAddCustomer: () => void
}

export function OverviewTab({
  stats,
  customers,
  payments,
  onNavigateTab,
  onOpenAddCustomer
}: OverviewTabProps) {
  const expiringCustomers = customers.filter(
    (c) => c.status === 'Expiring Soon' || c.status === 'Expired'
  )

  const kpis = [
    {
      title: 'Active Clients',
      value: stats.totalCustomers || customers.length,
      subtitle: `${stats.activeLicenses || 0} active subscriptions`,
      icon: <Users className="w-5 h-5 text-blue-400" />,
      bg: 'from-blue-500/10 to-indigo-500/10',
      border: 'border-blue-500/20',
      accent: 'text-blue-400',
    },
    {
      title: 'Cameras Managed',
      value: stats.totalCamerasManaged || 24,
      subtitle: 'Across all client facilities',
      icon: <Video className="w-5 h-5 text-purple-400" />,
      bg: 'from-purple-500/10 to-pink-500/10',
      border: 'border-purple-500/20',
      accent: 'text-purple-400',
    },
    {
      title: 'Monthly Recurring (MRR)',
      value: `₹${(stats.monthlyRecurringRevenue || 0).toLocaleString('en-IN')}`,
      subtitle: 'Estimated active monthly billing',
      icon: <CreditCard className="w-5 h-5 text-emerald-400" />,
      bg: 'from-emerald-500/10 to-teal-500/10',
      border: 'border-emerald-500/20',
      accent: 'text-emerald-400',
    },
    {
      title: 'Expiring Licenses',
      value: stats.expiringSoon || expiringCustomers.length,
      subtitle: 'Action required in ≤ 15 days',
      icon: <AlertTriangle className="w-5 h-5 text-amber-400" />,
      bg: 'from-amber-500/10 to-orange-500/10',
      border: 'border-amber-500/20',
      accent: 'text-amber-400',
    },
  ]

  return (
    <div className="space-y-6">
      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi, idx) => (
          <div
            key={idx}
            className={cn(
              'p-5 rounded-2xl border bg-gradient-to-br backdrop-blur-md relative overflow-hidden shadow-lg transition-all hover:scale-[1.01]',
              kpi.bg,
              kpi.border
            )}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                {kpi.title}
              </span>
              <div className="w-10 h-10 rounded-xl bg-background/60 border border-white/10 flex items-center justify-center">
                {kpi.icon}
              </div>
            </div>
            <div className="mt-3">
              <div className={cn('text-2xl font-black tracking-tight', kpi.accent)}>
                {kpi.value}
              </div>
              <p className="text-xs text-muted-foreground mt-1">{kpi.subtitle}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Expiring Soon Banner */}
      {expiringCustomers.length > 0 && (
        <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-md">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5 text-amber-400 animate-pulse" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-amber-300">
                {expiringCustomers.length} Customer License(s) Expiring Soon
              </h4>
              <p className="text-xs text-amber-400/80 mt-0.5">
                {expiringCustomers.map((c) => c.companyName).join(', ')} require license renewal.
              </p>
            </div>
          </div>
          <button
            onClick={() => onNavigateTab('licenses')}
            className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-bold text-xs flex items-center gap-1.5 transition-all shrink-0 shadow"
          >
            Manage Renewals <ArrowUpRight className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Main Grid: Recent Clients & Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Client Deployments */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-card border border-border/80 shadow-md space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-foreground">Client Deployments</h3>
              <p className="text-xs text-muted-foreground">Active enterprise sites and provisions</p>
            </div>
            <button
              onClick={() => onNavigateTab('customers')}
              className="text-xs font-semibold text-primary hover:underline flex items-center gap-1"
            >
              View All Clients ({customers.length}) →
            </button>
          </div>

          <div className="space-y-3">
            {customers.slice(0, 4).map((cust) => (
              <div
                key={cust.id}
                className="p-4 rounded-xl bg-muted/15 border border-border/60 hover:border-primary/40 transition-all flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center font-bold text-primary shrink-0">
                    {cust.companyName.charAt(0)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-foreground">{cust.companyName}</span>
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
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                      <span>{cust.siteLocation}</span>
                      <span>•</span>
                      <span>{cust.activeCameras} / {cust.maxCameras} Cams</span>
                      <span>•</span>
                      <span className="text-primary font-mono">{cust.duration}</span>
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-center">
                  <span className="text-xs font-mono font-semibold text-emerald-400">
                    ₹{cust.monthlyFee?.toLocaleString('en-IN')}/mo
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Provisioning Actions & Modules */}
        <div className="p-6 rounded-2xl bg-card border border-border/80 shadow-md space-y-5">
          <div>
            <h3 className="text-base font-bold text-foreground">Solution Controls</h3>
            <p className="text-xs text-muted-foreground">Deploy AI features to customers</p>
          </div>

          <button
            onClick={onOpenAddCustomer}
            className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-primary to-indigo-600 hover:from-primary/90 hover:to-indigo-500 text-white font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-primary/20 transition-all hover:scale-[1.02]"
          >
            <Sparkles className="w-4 h-4" /> + Onboard New Client
          </button>

          <div className="pt-3 border-t border-border/60 space-y-3">
            <span className="text-xs font-bold uppercase text-muted-foreground tracking-wider">
              Available AI Capabilities
            </span>
            <div className="space-y-2">
              {[
                { name: 'Safety & PPE Compliance', icon: '🦺' },
                { name: 'Fire & Smoke Early Warning', icon: '🔥' },
                { name: 'ANPR & Barrier Gates', icon: '🚗' },
                { name: 'Face Attendance & Watchlist', icon: '👥' },
                { name: 'Visitor Management (VMS)', icon: '📋' },
                { name: 'AI Voice Assistant (Hands-Free)', icon: '🎙️' },
              ].map((m, i) => (
                <div key={i} className="flex items-center justify-between text-xs py-1 text-muted-foreground">
                  <span className="flex items-center gap-2">
                    <span>{m.icon}</span>
                    <span className="text-foreground/90 font-medium">{m.name}</span>
                  </span>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
