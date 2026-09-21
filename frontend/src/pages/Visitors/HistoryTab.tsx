import React, { useEffect, useState, useMemo } from 'react'
import { 
  Download, 
  Search, 
  Users, 
  UserCheck, 
  Clock, 
  LogIn, 
  LogOut, 
  Calendar, 
  Building2, 
  Phone, 
  Mail, 
  Eye, 
  X, 
  ChevronLeft, 
  ChevronRight, 
  CheckCircle2, 
  Clock3, 
  ShieldCheck,
  Filter
} from 'lucide-react'
import { api } from '@/api/api'
import { cn } from '@/utils/utils'

export type DayVisitorItem = {
  visit_id?: string
  visitor_id: string
  name: string
  role: string
  email?: string
  phone?: string
  photo?: string
  company?: string
  host_name?: string
  purpose?: string
  entry_time?: string
  exit_time?: string
  entry_camera?: string
  exit_camera?: string
  duration_minutes?: number
  status: 'ACTIVE' | 'COMPLETED' | 'EXPECTED'
  confidence?: number
  snapshot_path?: string
  is_return?: boolean
}

const formatTime = (iso?: string) => {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return '—'
  }
}

export default function HistoryTab() {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10))
  const [activeFilter, setActiveFilter] = useState<'all' | 'active' | 'completed' | 'expected'>('all')
  const [search, setSearch] = useState('')
  const [summaryData, setSummaryData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [selectedVisitor, setSelectedVisitor] = useState<DayVisitorItem | null>(null)

  const fetchDayData = async (selectedDay: string) => {
    setLoading(true)
    try {
      const res = await api.get('/api/plugins/visitor/day-summary', {
        params: { day: selectedDay }
      })
      if (res.data) {
        setSummaryData(res.data)
      }
    } catch (err) {
      console.error("Failed to load day-wise visitor data", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDayData(day)
  }, [day])

  const items: DayVisitorItem[] = useMemo(() => {
    return summaryData?.items || []
  }, [summaryData])

  // Change date helpers
  const changeDateBy = (offsetDays: number) => {
    const current = new Date(day)
    current.setDate(current.getDate() + offsetDays)
    const newStr = current.toISOString().slice(0, 10)
    setDay(newStr)
  }

  const setToday = () => {
    setDay(new Date().toISOString().slice(0, 10))
  }

  // Filter items
  const filteredList = useMemo(() => {
    let result = items

    if (activeFilter === 'active') {
      result = items.filter(i => i.status === 'ACTIVE')
    } else if (activeFilter === 'completed') {
      result = items.filter(i => i.status === 'COMPLETED')
    } else if (activeFilter === 'expected') {
      result = items.filter(i => i.status === 'EXPECTED')
    }

    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(r =>
        r.name?.toLowerCase().includes(q) ||
        r.visitor_id?.toLowerCase().includes(q) ||
        (r.company || '').toLowerCase().includes(q) ||
        (r.host_name || '').toLowerCase().includes(q) ||
        (r.purpose || '').toLowerCase().includes(q)
      )
    }

    return result
  }, [items, activeFilter, search])

  // Export CSV
  const handleExportCsv = () => {
    const headers = ['Visitor ID', 'Name', 'Role', 'Company', 'Host Name', 'Purpose', 'Status', 'Entry Time', 'Exit Time', 'Duration (Mins)', 'Camera']
    const csvRows = [headers.join(',')]

    filteredList.forEach(item => {
      csvRows.push([
        `"${item.visitor_id}"`,
        `"${item.name}"`,
        `"${item.role}"`,
        `"${item.company || ''}"`,
        `"${item.host_name || ''}"`,
        `"${item.purpose || ''}"`,
        `"${item.status}"`,
        `"${item.entry_time ? new Date(item.entry_time).toLocaleTimeString() : ''}"`,
        `"${item.exit_time ? new Date(item.exit_time).toLocaleTimeString() : ''}"`,
        `"${item.duration_minutes || ''}"`,
        `"${item.entry_camera || ''}"`
      ].join(','))
    })

    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `visitors_${day}_${activeFilter}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const activeCount = items.filter(i => i.status === 'ACTIVE').length
  const completedCount = items.filter(i => i.status === 'COMPLETED').length
  const expectedCount = items.filter(i => i.status === 'EXPECTED').length

  return (
    <div className="space-y-5 text-slate-900">
      {/* Header & Date Selector */}
      <div className="flex flex-col md:flex-row justify-between md:items-center gap-4 bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Calendar className="w-5 h-5 text-blue-600" /> Day-Wise Visitor Register & Log
          </h2>
          <p className="text-xs text-slate-500">
            Comprehensive daily log of visitor entries, hosts, stay duration, and exit records.
          </p>
        </div>

        {/* Date Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center bg-slate-100 border border-slate-300 rounded-lg p-1 shadow-2xs">
            <button
              onClick={() => changeDateBy(-1)}
              className="p-1 rounded hover:bg-white text-slate-600 hover:text-slate-900 transition-all cursor-pointer"
              title="Previous Day"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <input
              type="date"
              value={day}
              max={new Date().toISOString().slice(0, 10)}
              onChange={e => setDay(e.target.value)}
              className="bg-transparent border-none text-xs font-bold text-slate-900 px-2 focus:outline-none cursor-pointer"
            />
            <button
              onClick={() => changeDateBy(1)}
              disabled={day === new Date().toISOString().slice(0, 10)}
              className="p-1 rounded hover:bg-white text-slate-600 hover:text-slate-900 disabled:opacity-40 disabled:hover:bg-transparent transition-all cursor-pointer"
              title="Next Day"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          <button
            onClick={setToday}
            className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-bold text-slate-700 border border-slate-300 transition-all cursor-pointer shadow-2xs"
          >
            Today
          </button>

          <button
            onClick={handleExportCsv}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition-all shadow-xs cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" /> Export CSV
          </button>
        </div>
      </div>

      {/* 4 Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <button
          onClick={() => setActiveFilter('all')}
          className={cn(
            "p-3.5 rounded-xl border text-left transition-all cursor-pointer shadow-xs flex items-center justify-between",
            activeFilter === 'all'
              ? "bg-blue-50 border-blue-400 ring-2 ring-blue-500/20 shadow-md"
              : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
          )}
        >
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-blue-100 text-blue-700">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] uppercase font-bold tracking-wider text-slate-500">Total Visitors</div>
              <div className="text-xs font-medium text-slate-600">कुल आगंतुक</div>
            </div>
          </div>
          <span className="text-2xl font-black text-blue-700">{items.length}</span>
        </button>

        <button
          onClick={() => setActiveFilter('active')}
          className={cn(
            "p-3.5 rounded-xl border text-left transition-all cursor-pointer shadow-xs flex items-center justify-between",
            activeFilter === 'active'
              ? "bg-emerald-50 border-emerald-400 ring-2 ring-emerald-500/20 shadow-md"
              : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
          )}
        >
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-emerald-100 text-emerald-700">
              <LogIn className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] uppercase font-bold tracking-wider text-slate-500">Active Inside</div>
              <div className="text-xs font-medium text-slate-600">वर्तमान में अंदर हैं</div>
            </div>
          </div>
          <span className="text-2xl font-black text-emerald-700">{activeCount}</span>
        </button>

        <button
          onClick={() => setActiveFilter('completed')}
          className={cn(
            "p-3.5 rounded-xl border text-left transition-all cursor-pointer shadow-xs flex items-center justify-between",
            activeFilter === 'completed'
              ? "bg-purple-50 border-purple-400 ring-2 ring-purple-500/20 shadow-md"
              : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
          )}
        >
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-purple-100 text-purple-700">
              <LogOut className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] uppercase font-bold tracking-wider text-slate-500">Completed Visits</div>
              <div className="text-xs font-medium text-slate-600">प्रस्थान कर चुके</div>
            </div>
          </div>
          <span className="text-2xl font-black text-purple-700">{completedCount}</span>
        </button>

        <button
          onClick={() => setActiveFilter('expected')}
          className={cn(
            "p-3.5 rounded-xl border text-left transition-all cursor-pointer shadow-xs flex items-center justify-between",
            activeFilter === 'expected'
              ? "bg-amber-50 border-amber-400 ring-2 ring-amber-500/20 shadow-md"
              : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
          )}
        >
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-amber-100 text-amber-700">
              <Clock3 className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] uppercase font-bold tracking-wider text-slate-500">Pre-Registered</div>
              <div className="text-xs font-medium text-slate-600">अपेक्षित (Appointment)</div>
            </div>
          </div>
          <span className="text-2xl font-black text-amber-700">{expectedCount}</span>
        </button>
      </div>

      {/* Main Table Container */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
        {/* Search & Counter Toolbar */}
        <div className="p-4 border-b border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/50">
          <div className="relative w-full sm:w-96">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by visitor name, ID (VIS-0001), host, company..."
              className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-slate-300 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 font-medium"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            <span className="text-xs font-bold text-slate-600 px-3 py-1.5 bg-slate-200/60 rounded-lg">
              {filteredList.length} of {items.length} records on {day}
            </span>
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-[11px] uppercase font-bold tracking-wider text-slate-500 bg-slate-100/75 border-b border-slate-200">
              <tr>
                <th className="px-5 py-3.5">Visitor Profile</th>
                <th className="px-4 py-3.5">Company / Firm</th>
                <th className="px-4 py-3.5">Host / Purpose</th>
                <th className="px-4 py-3.5">Status</th>
                <th className="px-4 py-3.5">Entry Time</th>
                <th className="px-4 py-3.5">Exit Time</th>
                <th className="px-4 py-3.5 text-center">Duration</th>
                <th className="px-4 py-3.5">Gate / Camera</th>
                <th className="px-4 py-3.5 text-right">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredList.map(item => {
                const isActive = item.status === 'ACTIVE'
                const isCompleted = item.status === 'COMPLETED'
                const isExpected = item.status === 'EXPECTED'

                return (
                  <tr
                    key={item.visit_id || item.visitor_id}
                    onClick={() => setSelectedVisitor(item)}
                    className="hover:bg-blue-50/40 transition-colors cursor-pointer group"
                  >
                    {/* Visitor Profile */}
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-slate-200 border border-slate-300 overflow-hidden flex items-center justify-center shrink-0 shadow-xs relative">
                          {item.photo ? (
                            <img
                              src={item.photo.startsWith('/') ? item.photo : `/${item.photo}`}
                              alt={item.name}
                              className="w-full h-full object-cover"
                              onError={e => {
                                const target = e.target as HTMLImageElement
                                target.style.display = 'none'
                              }}
                            />
                          ) : (
                            <span className="font-bold text-sm text-slate-600">
                              {item.name.slice(0, 2).toUpperCase()}
                            </span>
                          )}
                          {isActive && (
                            <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-500 border-2 border-white rounded-full animate-pulse" />
                          )}
                        </div>
                        <div>
                          <div className="font-bold text-slate-900 group-hover:text-blue-600 transition-colors flex items-center gap-1.5">
                            {item.name}
                            {item.is_return && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 font-bold">
                                Returning
                              </span>
                            )}
                          </div>
                          <div className="text-xs font-mono text-slate-500 font-semibold">
                            {item.visitor_id}
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* Company */}
                    <td className="px-4 py-3.5">
                      <div className="font-medium text-slate-800 text-xs flex items-center gap-1">
                        <Building2 className="w-3.5 h-3.5 text-slate-400" />
                        {item.company || 'Direct Visitor'}
                      </div>
                    </td>

                    {/* Host & Purpose */}
                    <td className="px-4 py-3.5">
                      <div className="font-bold text-slate-800 text-xs">
                        {item.host_name || 'Front Desk'}
                      </div>
                      <div className="text-[11px] text-slate-500">
                        {item.purpose || 'Site Meeting'}
                      </div>
                    </td>

                    {/* Status Badge */}
                    <td className="px-4 py-3.5">
                      {isActive ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-300 text-emerald-800 text-xs font-bold">
                          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" /> Inside Premise
                        </span>
                      ) : isCompleted ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-100 border border-slate-300 text-slate-700 text-xs font-bold">
                          <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" /> Departed
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-300 text-amber-800 text-xs font-bold">
                          <Clock3 className="w-3.5 h-3.5 text-amber-600" /> Expected
                        </span>
                      )}
                    </td>

                    {/* Entry Time */}
                    <td className="px-4 py-3.5 font-mono text-xs">
                      {item.entry_time ? (
                        <span className="inline-flex items-center gap-1.5 text-emerald-700 font-bold bg-emerald-50/80 px-2 py-0.5 rounded border border-emerald-200">
                          <LogIn className="w-3.5 h-3.5 text-emerald-600" /> {formatTime(item.entry_time)}
                        </span>
                      ) : (
                        <span className="text-slate-400 italic">Pre-scheduled</span>
                      )}
                    </td>

                    {/* Exit Time */}
                    <td className="px-4 py-3.5 font-mono text-xs">
                      {item.exit_time ? (
                        <span className="inline-flex items-center gap-1.5 font-bold px-2 py-0.5 rounded border bg-slate-100 text-slate-700 border-slate-200">
                          <LogOut className="w-3.5 h-3.5 text-slate-600" /> {formatTime(item.exit_time)}
                        </span>
                      ) : isActive ? (
                        <span className="text-xs text-emerald-600 font-bold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100">
                          Active In
                        </span>
                      ) : (
                        <span className="text-slate-400 italic">—</span>
                      )}
                    </td>

                    {/* Duration */}
                    <td className="px-4 py-3.5 text-center font-mono text-xs">
                      {item.duration_minutes != null ? (
                        <span className="px-2.5 py-1 rounded-lg bg-blue-50 text-blue-800 border border-blue-200 font-bold">
                          {item.duration_minutes < 60
                            ? `${Math.round(item.duration_minutes)}m`
                            : `${Math.floor(item.duration_minutes / 60)}h ${Math.round(item.duration_minutes % 60)}m`}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>

                    {/* Gate / Camera */}
                    <td className="px-4 py-3.5 text-xs text-slate-600 font-mono">
                      {item.entry_camera ? (
                        <span className="px-2 py-0.5 bg-slate-100 rounded border border-slate-200 font-semibold">
                          {item.entry_camera.split('/').pop() || item.entry_camera}
                        </span>
                      ) : (
                        <span className="text-slate-400 italic">VMS App</span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3.5 text-right">
                      <button
                        onClick={e => {
                          e.stopPropagation()
                          setSelectedVisitor(item)
                        }}
                        className="p-1.5 rounded-lg bg-slate-100 hover:bg-blue-600 hover:text-white text-slate-600 transition-all cursor-pointer shadow-2xs"
                        title="View Visitor Pass & Full History"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                )
              })}

              {!loading && filteredList.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-5 py-16 text-center text-slate-500">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <Users className="w-10 h-10 text-slate-300" />
                      <div className="font-bold text-slate-700">No visitor records for {day}</div>
                      <div className="text-xs text-slate-400 max-w-sm">
                        No entries match your search query or selected filter.
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Visitor Pass & Detail Modal */}
      {selectedVisitor && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header Badge */}
            <div className="p-6 bg-gradient-to-r from-blue-600 to-indigo-700 text-white flex items-start justify-between">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-white/20 border-2 border-white/40 overflow-hidden shrink-0 flex items-center justify-center shadow-md">
                  {selectedVisitor.photo ? (
                    <img
                      src={selectedVisitor.photo.startsWith('/') ? selectedVisitor.photo : `/${selectedVisitor.photo}`}
                      alt={selectedVisitor.name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <span className="text-2xl font-black text-white">
                      {selectedVisitor.name.slice(0, 2).toUpperCase()}
                    </span>
                  )}
                </div>
                <div>
                  <h3 className="text-xl font-black text-white leading-tight">{selectedVisitor.name}</h3>
                  <div className="text-xs font-mono text-blue-100 font-bold mt-0.5">
                    Visitor Badge: {selectedVisitor.visitor_id}
                  </div>
                  <div className="inline-block mt-1 px-2 py-0.5 rounded bg-white/20 text-white text-[10px] font-black uppercase tracking-wider">
                    {selectedVisitor.role} PASS
                  </div>
                </div>
              </div>
              <button
                onClick={() => setSelectedVisitor(null)}
                className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-all cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200">
                <div>
                  <div className="text-[10px] uppercase font-bold text-slate-500">Company / Organization</div>
                  <div className="text-sm font-bold text-slate-800">{selectedVisitor.company || 'Direct Visitor'}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase font-bold text-slate-500">Host / Department</div>
                  <div className="text-sm font-bold text-slate-800">{selectedVisitor.host_name || 'Front Desk'}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase font-bold text-slate-500">Purpose of Visit</div>
                  <div className="text-xs font-semibold text-slate-700">{selectedVisitor.purpose || 'Meeting / Site Visit'}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase font-bold text-slate-500">Pass Status</div>
                  <div className="text-xs font-bold text-slate-800">
                    {selectedVisitor.status === 'ACTIVE'
                      ? '🟢 In Premise'
                      : selectedVisitor.status === 'COMPLETED'
                      ? '⚪ Departed'
                      : '🟡 Pre-Scheduled'}
                  </div>
                </div>
                {selectedVisitor.phone && (
                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-500">Phone Number</div>
                    <div className="text-xs font-semibold text-slate-700 flex items-center gap-1 mt-0.5">
                      <Phone className="w-3.5 h-3.5 text-blue-600" /> {selectedVisitor.phone}
                    </div>
                  </div>
                )}
                {selectedVisitor.email && (
                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-500">Email Address</div>
                    <div className="text-xs font-semibold text-slate-700 flex items-center gap-1 mt-0.5">
                      <Mail className="w-3.5 h-3.5 text-blue-600" /> {selectedVisitor.email}
                    </div>
                  </div>
                )}
              </div>

              {/* Time Breakdown */}
              <div className="border border-slate-200 rounded-xl p-4 bg-white shadow-2xs space-y-3">
                <h4 className="text-xs uppercase font-bold tracking-wider text-slate-600 flex items-center gap-2">
                  <Clock className="w-4 h-4 text-blue-600" /> Visit Timestamps & Verification
                </h4>

                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-200">
                    <div className="text-[10px] uppercase font-bold text-emerald-700">Check-In</div>
                    <div className="text-sm font-black text-emerald-900 mt-1">{formatTime(selectedVisitor.entry_time)}</div>
                  </div>
                  <div className="p-3 bg-purple-50 rounded-lg border border-purple-200">
                    <div className="text-[10px] uppercase font-bold text-purple-700">Check-Out</div>
                    <div className="text-sm font-black text-purple-900 mt-1">{formatTime(selectedVisitor.exit_time)}</div>
                  </div>
                  <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                    <div className="text-[10px] uppercase font-bold text-blue-700">Total Duration</div>
                    <div className="text-sm font-black text-blue-900 mt-1">
                      {selectedVisitor.duration_minutes != null
                        ? `${Math.round(selectedVisitor.duration_minutes)}m`
                        : 'Active'}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end">
              <button
                onClick={() => setSelectedVisitor(null)}
                className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-sm font-bold transition-all cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

