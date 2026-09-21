import React, { useState } from 'react'
import {
  CreditCard,
  CheckCircle2,
  Plus,
  Search,
  ArrowUpRight,
  Download,
  Calendar,
  DollarSign,
  FileText,
  X
} from 'lucide-react'
import { cn } from '@/utils/utils'

interface BillingPaymentsTabProps {
  payments: any[]
  customers: any[]
  onRecordPayment: (payment: any) => Promise<void>
}

export function BillingPaymentsTab({
  payments,
  customers,
  onRecordPayment,
}: BillingPaymentsTabProps) {
  const [searchTerm, setSearchTerm] = useState('')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const [formData, setFormData] = useState({
    customerId: customers[0]?.id || '',
    amount: 14990,
    plan: 'Enterprise 1 Year Plan',
    paymentMethod: 'UPI / Direct Bank Transfer',
    transactionId: '',
    durationMonths: 12,
  })

  const totalCollected = payments
    .filter((p) => p.status === 'Paid')
    .reduce((sum, p) => sum + (p.amount || 0), 0)

  const filteredPayments = payments.filter(
    (p) =>
      p.companyName?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.id?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.transactionId?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const handleCreatePayment = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSaving(true)
    try {
      await onRecordPayment(formData)
      setIsModalOpen(false)
    } catch (err) {
      console.error('Failed to record payment:', err)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Top Metric & Action Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10 border border-emerald-500/20 shadow-md">
          <span className="text-xs font-bold text-muted-foreground uppercase">Total Revenue Collected</span>
          <div className="text-2xl font-black text-emerald-400 mt-1">
            ₹{totalCollected.toLocaleString('en-IN')}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">{payments.length} Invoices processed</p>
        </div>

        <div className="p-5 rounded-2xl bg-card border border-border shadow-md flex items-center justify-between sm:col-span-2">
          <div>
            <h4 className="font-bold text-sm text-foreground">Customer Payments & Billing Hub</h4>
            <p className="text-xs text-muted-foreground mt-0.5">
              Live ledger of client subscription renewals and direct payment logs.
            </p>
          </div>
          <button
            onClick={() => {
              if (customers.length > 0) {
                setFormData((prev) => ({ ...prev, customerId: customers[0].id }))
              }
              setIsModalOpen(true)
            }}
            className="px-4 py-2 rounded-xl bg-primary hover:bg-primary/90 text-white font-bold text-xs flex items-center gap-2 shadow-lg shadow-primary/20 shrink-0"
          >
            <Plus className="w-4 h-4" /> Record New Payment
          </button>
        </div>
      </div>

      {/* Search Bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search invoice, client, txn..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-card border border-border rounded-xl pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {/* Payments Table */}
      <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-lg">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/20 border-b border-border text-xs uppercase font-bold text-muted-foreground">
              <tr>
                <th className="py-3.5 px-4">Invoice #</th>
                <th className="py-3.5 px-4">Client Organization</th>
                <th className="py-3.5 px-4">Plan / Package</th>
                <th className="py-3.5 px-4">Amount</th>
                <th className="py-3.5 px-4">Payment Method</th>
                <th className="py-3.5 px-4">Txn ID / Ref</th>
                <th className="py-3.5 px-4">Date</th>
                <th className="py-3.5 px-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {filteredPayments.map((p) => (
                <tr key={p.id} className="hover:bg-muted/10 transition-colors">
                  <td className="py-4 px-4 font-mono text-xs font-bold text-primary flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-primary/70" /> {p.id}
                  </td>
                  <td className="py-4 px-4 font-semibold text-foreground">{p.companyName}</td>
                  <td className="py-4 px-4 text-xs text-muted-foreground">{p.plan}</td>
                  <td className="py-4 px-4 font-mono font-bold text-emerald-400">
                    ₹{p.amount?.toLocaleString('en-IN')}
                  </td>
                  <td className="py-4 px-4 text-xs text-foreground/90">{p.paymentMethod}</td>
                  <td className="py-4 px-4 font-mono text-xs text-muted-foreground">{p.transactionId}</td>
                  <td className="py-4 px-4 text-xs text-muted-foreground">{p.date}</td>
                  <td className="py-4 px-4">
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400">
                      {p.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Record Payment Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl w-full max-w-lg p-6 space-y-5 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="font-bold text-base text-foreground flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-primary" /> Record Customer Payment / Renewal
              </h3>
              <button onClick={() => setIsModalOpen(false)} className="p-1 rounded-lg hover:bg-muted text-muted-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreatePayment} className="space-y-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold uppercase text-foreground">Select Customer *</label>
                <select
                  value={formData.customerId}
                  onChange={(e) => setFormData({ ...formData, customerId: e.target.value })}
                  className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.companyName} ({c.siteLocation})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold uppercase text-foreground">Payment Amount (₹) *</label>
                  <input
                    type="number"
                    required
                    value={formData.amount}
                    onChange={(e) => setFormData({ ...formData, amount: parseFloat(e.target.value) })}
                    className="bg-background border border-border rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold uppercase text-foreground">Extend Duration</label>
                  <select
                    value={formData.durationMonths}
                    onChange={(e) => setFormData({ ...formData, durationMonths: parseInt(e.target.value) })}
                    className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value={1}>+1 Month</option>
                    <option value={3}>+3 Months</option>
                    <option value={6}>+6 Months</option>
                    <option value={12}>+1 Year</option>
                  </select>
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold uppercase text-foreground">Plan Description</label>
                <input
                  type="text"
                  value={formData.plan}
                  onChange={(e) => setFormData({ ...formData, plan: e.target.value })}
                  placeholder="e.g. Annual Enterprise AI Suite"
                  className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold uppercase text-foreground">Payment Mode</label>
                  <select
                    value={formData.paymentMethod}
                    onChange={(e) => setFormData({ ...formData, paymentMethod: e.target.value })}
                    className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="UPI / QR Code">UPI / QR Code</option>
                    <option value="NEFT / RTGS / Bank Transfer">NEFT / RTGS Transfer</option>
                    <option value="Credit / Debit Card">Credit / Debit Card</option>
                    <option value="Razorpay / Payment Gateway">Razorpay / Gateway</option>
                    <option value="Cheque / Cash">Cheque / Cash</option>
                  </select>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold uppercase text-foreground">Transaction ID / Ref</label>
                  <input
                    type="text"
                    value={formData.transactionId}
                    onChange={(e) => setFormData({ ...formData, transactionId: e.target.value })}
                    placeholder="e.g. UPI_88492019"
                    className="bg-background border border-border rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-xl border border-border hover:bg-muted text-sm text-muted-foreground"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="px-5 py-2 rounded-xl bg-primary hover:bg-primary/90 text-white font-bold text-sm shadow-md"
                >
                  {isSaving ? 'Recording...' : 'Record Payment & Extend License'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
