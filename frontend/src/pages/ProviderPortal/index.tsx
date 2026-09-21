import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ShieldCheck,
  Users,
  Key,
  CreditCard,
  LayoutDashboard,
  ExternalLink,
  Sparkles,
  RefreshCw,
  Building2,
  Lock,
  ArrowLeft
} from 'lucide-react'
import { api } from '@/api/api'
import { useToastStore } from '@/store/useToastStore'
import { cn } from '@/utils/utils'

import { OverviewTab } from './tabs/OverviewTab'
import { CustomerManagementTab } from './tabs/CustomerManagementTab'
import { LicenseEngineTab } from './tabs/LicenseEngineTab'
import { BillingPaymentsTab } from './tabs/BillingPaymentsTab'

export function ProviderPortal() {
  const [activeTab, setActiveTab] = useState<'overview' | 'customers' | 'licenses' | 'billing'>('overview')
  const [stats, setStats] = useState<any>({})
  const [customers, setCustomers] = useState<any[]>([])
  const [payments, setPayments] = useState<any[]>([])
  const [availableServices, setAvailableServices] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const addToast = useToastStore((s) => s.addToast)

  const loadAllData = async () => {
    setIsLoading(true)
    try {
      const [statsRes, custRes, payRes] = await Promise.all([
        api.get('/api/provider/stats'),
        api.get('/api/provider/customers'),
        api.get('/api/provider/payments'),
      ])

      setStats(statsRes.data || {})
      setCustomers(custRes.data?.customers || [])
      setPayments(payRes.data?.payments || [])
      setAvailableServices(statsRes.data?.availableServices || [])
    } catch (err: any) {
      console.error('Failed to load provider data:', err)
      addToast({
        title: 'Connection Error',
        message: 'Could not connect to Provider API. Showing local state.',
        type: 'warning',
      })
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadAllData()
  }, [])

  const handleSaveCustomer = async (custData: any) => {
    try {
      if (custData.id) {
        await api.put(`/api/provider/customers/${custData.id}`, custData)
        addToast({
          title: 'Customer Updated',
          message: `${custData.companyName} provisions updated successfully.`,
          type: 'success',
        })
      } else {
        await api.post('/api/provider/customers', custData)
        addToast({
          title: 'Customer Onboarded',
          message: `${custData.companyName} onboarded and license issued.`,
          type: 'success',
        })
      }
      await loadAllData()
    } catch (err: any) {
      addToast({
        title: 'Save Error',
        message: err.message || 'Failed to save customer',
        type: 'danger',
      })
    }
  }

  const handleDeleteCustomer = async (id: string) => {
    try {
      await api.delete(`/api/provider/customers/${id}`)
      addToast({
        title: 'Customer Removed',
        message: 'Client removed from provider hub.',
        type: 'default',
      })
      await loadAllData()
    } catch (err: any) {
      addToast({
        title: 'Delete Error',
        message: err.message || 'Failed to delete customer',
        type: 'danger',
      })
    }
  }

  const handleExtendLicense = async (customerId: string, duration: string) => {
    try {
      await api.put(`/api/provider/customers/${customerId}`, { duration })
      addToast({
        title: 'License Extended',
        message: `License successfully extended by ${duration}.`,
        type: 'success',
      })
      await loadAllData()
    } catch (err: any) {
      addToast({
        title: 'Extension Error',
        message: err.message || 'Failed to extend license',
        type: 'danger',
      })
    }
  }

  const handleRecordPayment = async (paymentData: any) => {
    try {
      await api.post('/api/provider/payments', paymentData)
      addToast({
        title: 'Payment Recorded',
        message: 'Payment logged and client license validity extended.',
        type: 'success',
      })
      await loadAllData()
    } catch (err: any) {
      addToast({
        title: 'Payment Error',
        message: err.message || 'Failed to record payment',
        type: 'danger',
      })
    }
  }

  const tabs = [
    { id: 'overview', label: 'Overview & Metrics', icon: <LayoutDashboard className="w-4 h-4" /> },
    { id: 'customers', label: `Clients & Provisioning (${customers.length})`, icon: <Users className="w-4 h-4" /> },
    { id: 'licenses', label: 'License Engine & Keys', icon: <Key className="w-4 h-4" /> },
    { id: 'billing', label: 'Billing & Invoices', icon: <CreditCard className="w-4 h-4" /> },
  ]

  return (
    <div className="min-h-screen bg-[#070b14] text-foreground flex flex-col font-sans">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-50 bg-[#0b1120]/90 backdrop-blur-md border-b border-border/70 px-6 py-3.5 flex items-center justify-between shadow-xl">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500/20 via-primary/30 to-purple-500/20 border border-primary/40 flex items-center justify-center shadow-[0_0_15px_rgba(99,102,241,0.3)]">
            <ShieldCheck className="w-5 h-5 text-primary animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-black tracking-tight text-white flex items-center gap-1.5">
                DevaVision AI <span className="text-primary font-mono text-xs px-2 py-0.5 rounded-full bg-primary/15 border border-primary/30">Provider Hub</span>
              </h1>
              <span className="hidden sm:inline-block text-[10px] uppercase font-bold text-amber-400 px-2 py-0.5 rounded-full bg-amber-400/10 border border-amber-400/20">
                Super Admin Mode
              </span>
            </div>
            <p className="text-xs text-muted-foreground">Multi-Tenant Client Provisioning & License Management</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadAllData}
            disabled={isLoading}
            className="p-2 rounded-xl bg-muted/20 hover:bg-muted/40 text-muted-foreground hover:text-foreground border border-border/50 transition-colors"
            title="Refresh Data"
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin text-primary')} />
          </button>

          {/* Quick Switch to Customer CCTV Dashboard */}
          <Link
            to="/"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 rounded-xl bg-muted/25 hover:bg-primary/20 text-foreground/90 hover:text-primary border border-border/80 hover:border-primary/40 text-xs font-bold flex items-center gap-2 transition-all shadow-sm"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Customer CCTV Portal <ExternalLink className="w-3 h-3 text-muted-foreground" />
          </Link>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-border/60 pb-1 overflow-x-auto custom-scrollbar">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={cn(
                'px-4 py-2.5 rounded-xl text-xs font-bold flex items-center gap-2 transition-all shrink-0',
                activeTab === tab.id
                  ? 'bg-primary text-white shadow-lg shadow-primary/25 scale-[1.02]'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/20'
              )}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab Contents */}
        {activeTab === 'overview' && (
          <OverviewTab
            stats={stats}
            customers={customers}
            payments={payments}
            onNavigateTab={(tab) => setActiveTab(tab as any)}
            onOpenAddCustomer={() => setActiveTab('customers')}
          />
        )}

        {activeTab === 'customers' && (
          <CustomerManagementTab
            customers={customers}
            availableServices={availableServices}
            onRefresh={loadAllData}
            onSaveCustomer={handleSaveCustomer}
            onDeleteCustomer={handleDeleteCustomer}
          />
        )}

        {activeTab === 'licenses' && (
          <LicenseEngineTab
            customers={customers}
            onExtendLicense={handleExtendLicense}
          />
        )}

        {activeTab === 'billing' && (
          <BillingPaymentsTab
            payments={payments}
            customers={customers}
            onRecordPayment={handleRecordPayment}
          />
        )}
      </main>
    </div>
  )
}
export default ProviderPortal
