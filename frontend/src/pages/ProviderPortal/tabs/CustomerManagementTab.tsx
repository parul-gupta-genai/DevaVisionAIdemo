import React, { useState } from 'react'
import {
  Users,
  Search,
  Plus,
  Edit2,
  Trash2,
  CheckCircle2,
  Calendar,
  Video,
  Key,
  Shield,
  Layers,
  X,
  Sparkles,
  Phone,
  Mail,
  MapPin
} from 'lucide-react'
import { cn } from '@/utils/utils'

interface CustomerManagementTabProps {
  customers: any[]
  availableServices: any[]
  onRefresh: () => void
  onSaveCustomer: (customer: any) => Promise<void>
  onDeleteCustomer: (id: string) => Promise<void>
}

export function CustomerManagementTab({
  customers,
  availableServices,
  onRefresh,
  onSaveCustomer,
  onDeleteCustomer,
}: CustomerManagementTabProps) {
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [editingCustomer, setEditingCustomer] = useState<any | null>(null)
  const [isNewModalOpen, setIsNewModalOpen] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  // Form State for New / Edit Customer
  const [formData, setFormData] = useState({
    companyName: '',
    clientName: '',
    email: '',
    phone: '',
    siteLocation: '',
    maxCameras: 8,
    duration: '1 Year',
    customExpiryDate: '',
    enabledServices: ['ppe_detection', 'fire_smoke', 'voice_assistant'] as string[],
  })

  const openEditModal = (cust: any) => {
    setEditingCustomer(cust)
    setFormData({
      companyName: cust.companyName || '',
      clientName: cust.clientName || '',
      email: cust.email || '',
      phone: cust.phone || '',
      siteLocation: cust.siteLocation || '',
      maxCameras: cust.maxCameras || 8,
      duration: cust.duration || '1 Year',
      customExpiryDate: cust.expiryDate || '',
      enabledServices: cust.enabledServices || [],
    })
  }

  const openNewModal = () => {
    setEditingCustomer(null)
    setFormData({
      companyName: '',
      clientName: '',
      email: '',
      phone: '',
      siteLocation: '',
      maxCameras: 8,
      duration: '1 Year',
      customExpiryDate: '',
      enabledServices: ['ppe_detection', 'fire_smoke', 'voice_assistant'],
    })
    setIsNewModalOpen(true)
  }

  const toggleService = (serviceId: string) => {
    setFormData((prev) => {
      const exists = prev.enabledServices.includes(serviceId)
      return {
        ...prev,
        enabledServices: exists
          ? prev.enabledServices.filter((id) => id !== serviceId)
          : [...prev.enabledServices, serviceId],
      }
    })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSaving(true)
    try {
      if (editingCustomer) {
        await onSaveCustomer({
          id: editingCustomer.id,
          ...formData,
        })
      } else {
        await onSaveCustomer(formData)
      }
      setIsNewModalOpen(false)
      setEditingCustomer(null)
      onRefresh()
    } catch (err) {
      console.error('Error saving customer:', err)
    } finally {
      setIsSaving(false)
    }
  }

  const filteredCustomers = customers.filter((c) => {
    const matchesSearch =
      c.companyName?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.clientName?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.siteLocation?.toLowerCase().includes(searchTerm.toLowerCase())
    if (statusFilter === 'all') return matchesSearch
    return matchesSearch && c.status?.toLowerCase() === statusFilter.toLowerCase()
  })

  return (
    <div className="space-y-6">
      {/* Top Controls Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="relative flex-1 sm:w-72">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search company, client, site..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-card border border-border rounded-xl pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-card border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="expiring soon">Expiring Soon</option>
            <option value="expired">Expired</option>
          </select>
        </div>

        <button
          onClick={openNewModal}
          className="w-full sm:w-auto px-4 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-white font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-primary/20 transition-all hover:scale-[1.02]"
        >
          <Plus className="w-4 h-4" /> Add New Customer
        </button>
      </div>

      {/* Customer Cards Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {filteredCustomers.map((cust) => (
          <div
            key={cust.id}
            className="p-6 rounded-2xl bg-card border border-border/80 hover:border-primary/40 transition-all shadow-md space-y-4 relative overflow-hidden group"
          >
            {/* Header */}
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary/20 to-indigo-500/20 border border-primary/30 flex items-center justify-center font-black text-lg text-primary">
                  {cust.companyName.charAt(0)}
                </div>
                <div>
                  <h3 className="font-bold text-base text-foreground flex items-center gap-2">
                    {cust.companyName}
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
                  </h3>
                  <p className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                    <MapPin className="w-3 h-3 text-primary/70" /> {cust.siteLocation}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => openEditModal(cust)}
                  className="p-2 rounded-lg bg-muted/20 hover:bg-primary/20 text-muted-foreground hover:text-primary transition-colors border border-border/50"
                  title="Edit Provisioning"
                >
                  <Edit2 className="w-4 h-4" />
                </button>
                <button
                  onClick={() => {
                    if (confirm(`Remove client ${cust.companyName}?`)) onDeleteCustomer(cust.id)
                  }}
                  className="p-2 rounded-lg bg-muted/20 hover:bg-danger/20 text-muted-foreground hover:text-danger transition-colors border border-border/50"
                  title="Delete Customer"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* License & Quota Row */}
            <div className="grid grid-cols-3 gap-2 p-3 rounded-xl bg-muted/15 border border-border/50 text-xs">
              <div>
                <span className="text-muted-foreground block text-[10px] uppercase font-bold">Duration</span>
                <span className="font-semibold text-foreground flex items-center gap-1 mt-0.5">
                  <Calendar className="w-3 h-3 text-primary" /> {cust.duration}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground block text-[10px] uppercase font-bold">Cameras</span>
                <span className="font-semibold text-foreground flex items-center gap-1 mt-0.5">
                  <Video className="w-3 h-3 text-purple-400" /> {cust.activeCameras} / {cust.maxCameras} Max
                </span>
              </div>
              <div>
                <span className="text-muted-foreground block text-[10px] uppercase font-bold">Expires</span>
                <span className="font-semibold text-foreground font-mono mt-0.5 block">{cust.expiryDate}</span>
              </div>
            </div>

            {/* License Key Badge */}
            <div className="flex items-center justify-between p-2.5 rounded-xl bg-background/50 border border-border/60 text-xs">
              <span className="flex items-center gap-1.5 text-muted-foreground font-medium">
                <Key className="w-3.5 h-3.5 text-amber-400" /> License Key:
              </span>
              <code className="font-mono text-primary font-bold tracking-wider">{cust.licenseKey}</code>
            </div>

            {/* Provisioned Services Badges */}
            <div className="space-y-1.5 pt-1">
              <span className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider block">
                Provisioned AI Modules ({cust.enabledServices?.length || 0})
              </span>
              <div className="flex flex-wrap gap-1.5">
                {(cust.enabledServices || []).map((srvId: string) => {
                  const srv = availableServices.find((s) => s.id === srvId)
                  return (
                    <span
                      key={srvId}
                      className="px-2.5 py-1 rounded-lg bg-primary/10 border border-primary/20 text-xs text-foreground font-medium flex items-center gap-1"
                    >
                      <span>{srv?.icon || '✨'}</span>
                      <span>{srv?.name || srvId}</span>
                    </span>
                  )
                })}
              </div>
            </div>

            {/* Contact Footer */}
            <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border/50">
              <span className="flex items-center gap-1">
                <Mail className="w-3 h-3" /> {cust.email}
              </span>
              <span className="font-mono font-bold text-emerald-400">
                ₹{cust.monthlyFee?.toLocaleString('en-IN')}/mo
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Onboard / Edit Customer Modal */}
      {(isNewModalOpen || editingCustomer) && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto custom-scrollbar p-6 space-y-6 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-primary/20 border border-primary/30 flex items-center justify-center">
                  <Sparkles className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-bold text-lg text-foreground">
                    {editingCustomer ? `Edit Provisioning: ${editingCustomer.companyName}` : 'Onboard New Customer Client'}
                  </h3>
                  <p className="text-xs text-muted-foreground">Select AI services, camera limits, and validity duration</p>
                </div>
              </div>
              <button
                onClick={() => {
                  setIsNewModalOpen(false)
                  setEditingCustomer(null)
                }}
                className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Company & Client Info */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold uppercase text-foreground">Company / Organization *</label>
                  <input
                    type="text"
                    required
                    value={formData.companyName}
                    onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                    placeholder="e.g. Tata Power Ltd."
                    className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold uppercase text-foreground">Contact Person *</label>
                  <input
                    type="text"
                    required
                    value={formData.clientName}
                    onChange={(e) => setFormData({ ...formData, clientName: e.target.value })}
                    placeholder="e.g. Rajesh Verma"
                    className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold uppercase text-foreground">Admin Email *</label>
                  <input
                    type="email"
                    required
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    placeholder="r.verma@tatapower.com"
                    className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold uppercase text-foreground">Phone Number</label>
                  <input
                    type="text"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                    placeholder="+91 98765 00000"
                    className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              {/* Site Location & Quota */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold uppercase text-foreground">Site Location / Facility</label>
                  <input
                    type="text"
                    value={formData.siteLocation}
                    onChange={(e) => setFormData({ ...formData, siteLocation: e.target.value })}
                    placeholder="Trombay Plant, Mumbai"
                    className="bg-background border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-bold uppercase text-foreground">Max Camera Limit ({formData.maxCameras} Cams)</label>
                  <input
                    type="range"
                    min="1"
                    max="64"
                    value={formData.maxCameras}
                    onChange={(e) => setFormData({ ...formData, maxCameras: parseInt(e.target.value) })}
                    className="w-full mt-2 accent-primary cursor-pointer"
                  />
                </div>
              </div>

              {/* License Duration */}
              <div className="p-4 rounded-xl bg-muted/15 border border-border/60 space-y-3">
                <label className="text-xs font-bold uppercase text-foreground flex items-center gap-1.5">
                  <Calendar className="w-4 h-4 text-primary" /> License Duration & Validity
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {['1 Month', '3 Months', '6 Months', '1 Year', 'Lifetime'].map((dur) => (
                    <button
                      key={dur}
                      type="button"
                      onClick={() => setFormData({ ...formData, duration: dur, customExpiryDate: '' })}
                      className={cn(
                        'py-2 px-3 rounded-lg text-xs font-bold border transition-all',
                        formData.duration === dur
                          ? 'border-primary bg-primary/20 text-primary'
                          : 'border-border bg-background/50 hover:bg-muted text-muted-foreground'
                      )}
                    >
                      {dur}
                    </button>
                  ))}
                </div>
              </div>

              {/* Feature Provisioning Checklist */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold uppercase text-foreground flex items-center gap-1.5">
                    <Layers className="w-4 h-4 text-primary" /> Select AI Services & Modules
                  </label>
                  <span className="text-xs text-muted-foreground">
                    {formData.enabledServices.length} Selected
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {availableServices.map((service) => {
                    const isSelected = formData.enabledServices.includes(service.id)
                    return (
                      <button
                        type="button"
                        key={service.id}
                        onClick={() => toggleService(service.id)}
                        className={cn(
                          'p-3 rounded-xl border text-left flex items-start justify-between gap-3 transition-all',
                          isSelected
                            ? 'border-primary bg-primary/10 shadow-[0_0_0_1px_rgba(99,102,241,0.3)]'
                            : 'border-border/70 bg-background/40 hover:bg-muted/30 opacity-70'
                        )}
                      >
                        <div className="flex items-start gap-2.5">
                          <span className="text-xl shrink-0">{service.icon}</span>
                          <div>
                            <span className="font-bold text-xs text-foreground block">{service.name}</span>
                            <span className="text-[10px] text-muted-foreground line-clamp-1 mt-0.5">
                              {service.description}
                            </span>
                          </div>
                        </div>
                        <div
                          className={cn(
                            'w-4 h-4 rounded-full border shrink-0 mt-0.5 flex items-center justify-center text-[10px]',
                            isSelected ? 'border-primary bg-primary text-white' : 'border-border'
                          )}
                        >
                          {isSelected && '✓'}
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Submit Buttons */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => {
                    setIsNewModalOpen(false)
                    setEditingCustomer(null)
                  }}
                  className="px-4 py-2 rounded-xl border border-border hover:bg-muted text-sm font-semibold text-muted-foreground"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="px-6 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-white text-sm font-bold shadow-lg shadow-primary/25 disabled:opacity-50"
                >
                  {isSaving ? 'Saving...' : editingCustomer ? 'Update License & Provisions' : 'Generate License & Save'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
