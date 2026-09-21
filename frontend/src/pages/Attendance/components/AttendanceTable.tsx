import React, { useMemo, useState } from 'react'
import { 
  LogIn, 
  LogOut, 
  Search, 
  Users, 
  UserCheck, 
  UserX, 
  Clock, 
  AlertTriangle, 
  Download, 
  Eye, 
  Building2, 
  Phone, 
  Mail, 
  CheckCircle2, 
  XCircle,
  ExternalLink,
  ShieldAlert,
  X
} from 'lucide-react'
import { cn } from '@/utils/utils'

export type AttendanceItem = {
  person_id: string
  person_code?: string
  name: string
  person_type: string
  department?: string
  company?: string
  email?: string
  phone?: string
  photo?: string
  enrolled?: boolean
  work_date?: string
  check_in_time?: string
  check_out_time?: string
  check_in_camera?: string
  check_out_camera?: string
  total_hours?: number
  sightings?: number
  status?: string // 'PRESENT' | 'ABSENT' | 'EARLY_EXIT' | 'PARTIAL'
  method?: string
  confidence?: number
}

interface AttendanceTableProps {
  presentRows: AttendanceItem[]
  absentRows: AttendanceItem[]
  allPersons?: AttendanceItem[]
  loading: boolean
  title?: string
  subtitle?: string
  onEnrolClick?: () => void
  onExportCsv?: () => void
}

const timeOf = (iso?: string) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'

export default function AttendanceTable({
  presentRows = [],
  absentRows = [],
  allPersons = [],
  loading = false,
  title,
  subtitle,
  onEnrolClick,
  onExportCsv
}: AttendanceTableProps) {
  const [activeFilter, setActiveFilter] = useState<'all' | 'present' | 'early' | 'absent'>('all')
  const [search, setSearch] = useState('')
  const [selectedPerson, setSelectedPerson] = useState<AttendanceItem | null>(null)

  const safePresentRows = useMemo(() => Array.isArray(presentRows) ? presentRows : [], [presentRows])
  const safeAbsentRows = useMemo(() => Array.isArray(absentRows) ? absentRows : [], [absentRows])
  const safeAllPersons = useMemo(() => Array.isArray(allPersons) ? allPersons : [], [allPersons])

  // Classify Early Departures:
  // 1. If checked out and total_hours < 7.5 hrs, OR
  // 2. Status is explicitly 'PARTIAL' or 'EARLY_EXIT', OR
  // 3. Checked out before 16:30
  const earlyDepartureRows = useMemo(() => {
    return safePresentRows.filter(r => {
      if (!r) return false
      if (r.status === 'PARTIAL' || r.status === 'EARLY_EXIT') return true
      if (r.check_out_time) {
        if (r.total_hours != null && r.total_hours > 0 && r.total_hours < 7.5) return true
        try {
          const outHour = new Date(r.check_out_time).getHours()
          if (!isNaN(outHour) && outHour < 17) return true
        } catch {
          // ignore date parse error
        }
      }
      return false
    })
  }, [safePresentRows])

  // Build unified items list
  const unifiedList = useMemo(() => {
    const presentMap = new Map<string, AttendanceItem>()
    safePresentRows.forEach(r => {
      if (r && r.person_id) presentMap.set(r.person_id, r)
    })

    const list: AttendanceItem[] = []

    // If allPersons list is provided, use it as the source of truth
    if (safeAllPersons.length > 0) {
      safeAllPersons.forEach(p => {
        if (!p || !p.person_id) return
        const pres = presentMap.get(p.person_id)
        if (pres) {
          const isEarly = earlyDepartureRows.some(e => e.person_id === p.person_id)
          list.push({
            ...p,
            ...pres,
            status: isEarly ? 'EARLY_EXIT' : pres.check_out_time ? 'COMPLETED' : 'IN_PREMISE'
          })
        } else {
          list.push({
            ...p,
            status: 'ABSENT'
          })
        }
      })
    } else {
      // Fallback: merge safePresentRows and safeAbsentRows
      safePresentRows.forEach(pres => {
        if (!pres || !pres.person_id) return
        const isEarly = earlyDepartureRows.some(e => e.person_id === pres.person_id)
        list.push({
          ...pres,
          status: isEarly ? 'EARLY_EXIT' : pres.check_out_time ? 'COMPLETED' : 'IN_PREMISE'
        })
      })
      safeAbsentRows.forEach(abs => {
        if (abs && abs.person_id && !presentMap.has(abs.person_id)) {
          list.push({
            ...abs,
            status: 'ABSENT'
          })
        }
      })
    }

    return list
  }, [safeAllPersons, safePresentRows, safeAbsentRows, earlyDepartureRows])

  // Filter based on active tab and search query
  const filteredList = useMemo(() => {
    let result = unifiedList

    if (activeFilter === 'present') {
      result = unifiedList.filter(item => item.status !== 'ABSENT')
    } else if (activeFilter === 'early') {
      result = unifiedList.filter(item => item.status === 'EARLY_EXIT')
    } else if (activeFilter === 'absent') {
      result = unifiedList.filter(item => item.status === 'ABSENT')
    }

    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(r =>
        r.name?.toLowerCase().includes(q) ||
        r.person_code?.toLowerCase().includes(q) ||
        r.department?.toLowerCase().includes(q) ||
        r.company?.toLowerCase().includes(q)
      )
    }

    return result
  }, [unifiedList, activeFilter, search])

  // Download filtered list as CSV
  const handleExportCsv = () => {
    if (onExportCsv) {
      onExportCsv()
      return
    }

    const headers = ['Name', 'Code', 'Role', 'Department', 'Company', 'Status', 'Check-In', 'Check-Out', 'Total Hours', 'Camera']
    const csvRows = [headers.join(',')]

    filteredList.forEach(item => {
      csvRows.push([
        `"${item.name}"`,
        `"${item.person_code || ''}"`,
        `"${item.person_type || ''}"`,
        `"${item.department || ''}"`,
        `"${item.company || ''}"`,
        `"${item.status || ''}"`,
        `"${item.check_in_time ? new Date(item.check_in_time).toLocaleTimeString() : ''}"`,
        `"${item.check_out_time ? new Date(item.check_out_time).toLocaleTimeString() : ''}"`,
        `"${item.total_hours != null ? item.total_hours.toFixed(2) : ''}"`,
        `"${item.check_in_camera || ''}"`
      ].join(','))
    })

    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `attendance_${activeFilter}_${new Date().toISOString().slice(0, 10)}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  return (
    <div className="space-y-4 text-slate-900">
      {/* Top Filter Buttons & Counts */}
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
              <div className="text-[11px] uppercase font-bold tracking-wider text-slate-500">Total Registered</div>
              <div className="text-xs font-medium text-slate-600">कुल पंजीकृत सूची</div>
            </div>
          </div>
          <span className="text-2xl font-black text-blue-700">{unifiedList.length}</span>
        </button>

        <button
          onClick={() => setActiveFilter('present')}
          className={cn(
            "p-3.5 rounded-xl border text-left transition-all cursor-pointer shadow-xs flex items-center justify-between",
            activeFilter === 'present'
              ? "bg-emerald-50 border-emerald-400 ring-2 ring-emerald-500/20 shadow-md"
              : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
          )}
        >
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-emerald-100 text-emerald-700">
              <UserCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] uppercase font-bold tracking-wider text-slate-500">Present Today</div>
              <div className="text-xs font-medium text-slate-600">उपस्थित (आए हुए)</div>
            </div>
          </div>
          <span className="text-2xl font-black text-emerald-700">{presentRows.length}</span>
        </button>

        <button
          onClick={() => setActiveFilter('early')}
          className={cn(
            "p-3.5 rounded-xl border text-left transition-all cursor-pointer shadow-xs flex items-center justify-between",
            activeFilter === 'early'
              ? "bg-amber-50 border-amber-400 ring-2 ring-amber-500/20 shadow-md"
              : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
          )}
        >
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-amber-100 text-amber-700">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] uppercase font-bold tracking-wider text-slate-500">Early Departures</div>
              <div className="text-xs font-medium text-slate-600">जल्दी चले गए (Half Day)</div>
            </div>
          </div>
          <span className="text-2xl font-black text-amber-700">{earlyDepartureRows.length}</span>
        </button>

        <button
          onClick={() => setActiveFilter('absent')}
          className={cn(
            "p-3.5 rounded-xl border text-left transition-all cursor-pointer shadow-xs flex items-center justify-between",
            activeFilter === 'absent'
              ? "bg-rose-50 border-rose-400 ring-2 ring-rose-500/20 shadow-md"
              : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
          )}
        >
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-rose-100 text-rose-700">
              <UserX className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] uppercase font-bold tracking-wider text-slate-500">Absent Today</div>
              <div className="text-xs font-medium text-slate-600">अनुपस्थित (नहीं आए)</div>
            </div>
          </div>
          <span className="text-2xl font-black text-rose-700">
            {unifiedList.filter(i => i.status === 'ABSENT').length}
          </span>
        </button>
      </div>

      {/* Main Table Card */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
        {/* Controls Toolbar */}
        <div className="p-4 border-b border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/50">
          <div className="relative w-full sm:w-96">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by name, badge code, department, contractor..."
              className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-slate-300 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            <span className="text-xs font-bold text-slate-600 px-3 py-1.5 bg-slate-200/60 rounded-lg">
              Showing {filteredList.length} of {unifiedList.length}
            </span>
            <button
              onClick={handleExportCsv}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-bold transition-all shadow-xs cursor-pointer"
            >
              <Download className="w-3.5 h-3.5 text-slate-600" /> Export CSV
            </button>
          </div>
        </div>

        {/* Attendance Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-[11px] uppercase font-bold tracking-wider text-slate-500 bg-slate-100/75 border-b border-slate-200">
              <tr>
                <th className="px-5 py-3.5">Person Profile</th>
                <th className="px-4 py-3.5">Role / Category</th>
                <th className="px-4 py-3.5">Department / Firm</th>
                <th className="px-4 py-3.5">Status</th>
                <th className="px-4 py-3.5">Check-In</th>
                <th className="px-4 py-3.5">Check-Out</th>
                <th className="px-4 py-3.5 text-center">Hours Worked</th>
                <th className="px-4 py-3.5">Camera / Device</th>
                <th className="px-4 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredList.map(item => {
                const isAbsent = item.status === 'ABSENT'
                const isEarly = item.status === 'EARLY_EXIT'
                const isCompleted = item.status === 'COMPLETED'
                const isInPremise = item.status === 'IN_PREMISE'

                return (
                  <tr
                    key={item.person_id}
                    onClick={() => setSelectedPerson(item)}
                    className="hover:bg-blue-50/40 transition-colors cursor-pointer group"
                  >
                    {/* Person Profile */}
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
                          {isInPremise && (
                            <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-500 border-2 border-white rounded-full" />
                          )}
                        </div>
                        <div>
                          <div className="font-bold text-slate-900 group-hover:text-blue-600 transition-colors flex items-center gap-1.5">
                            {item.name}
                            {item.enrolled && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-bold">
                                Face AI
                              </span>
                            )}
                          </div>
                          <div className="text-xs font-mono text-slate-500 font-semibold">
                            {item.person_code || item.person_id}
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* Role / Type */}
                    <td className="px-4 py-3.5">
                      <span className="px-2.5 py-1 rounded-md bg-slate-100 border border-slate-200 text-xs font-bold text-slate-700">
                        {item.person_type}
                      </span>
                    </td>

                    {/* Department / Company */}
                    <td className="px-4 py-3.5">
                      <div className="font-medium text-slate-800 text-xs">
                        {item.department || 'General'}
                      </div>
                      <div className="text-[11px] text-slate-500">
                        {item.company || 'Direct'}
                      </div>
                    </td>

                    {/* Status Badge */}
                    <td className="px-4 py-3.5">
                      {isAbsent ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-rose-50 border border-rose-200 text-rose-700 text-xs font-bold">
                          <XCircle className="w-3.5 h-3.5" /> Absent (अनुपस्थित)
                        </span>
                      ) : isEarly ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-300 text-amber-800 text-xs font-bold">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> Early Exit (जल्दी गए)
                        </span>
                      ) : isInPremise ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-300 text-emerald-800 text-xs font-bold">
                          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" /> On Site (अंदर हैं)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-100 border border-slate-300 text-slate-700 text-xs font-bold">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Shift Completed
                        </span>
                      )}
                    </td>

                    {/* Check-In */}
                    <td className="px-4 py-3.5 font-mono text-xs">
                      {item.check_in_time ? (
                        <span className="inline-flex items-center gap-1.5 text-emerald-700 font-bold bg-emerald-50/80 px-2 py-0.5 rounded border border-emerald-200">
                          <LogIn className="w-3.5 h-3.5 text-emerald-600" /> {timeOf(item.check_in_time)}
                        </span>
                      ) : (
                        <span className="text-slate-400 italic">—</span>
                      )}
                    </td>

                    {/* Check-Out */}
                    <td className="px-4 py-3.5 font-mono text-xs">
                      {item.check_out_time ? (
                        <span className={cn(
                          "inline-flex items-center gap-1.5 font-bold px-2 py-0.5 rounded border",
                          isEarly
                            ? "bg-amber-50 text-amber-800 border-amber-200"
                            : "bg-slate-100 text-slate-700 border-slate-200"
                        )}>
                          <LogOut className="w-3.5 h-3.5 text-amber-600" /> {timeOf(item.check_out_time)}
                        </span>
                      ) : isInPremise ? (
                        <span className="text-xs text-emerald-600 font-bold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100">
                          Active In
                        </span>
                      ) : (
                        <span className="text-slate-400 italic">—</span>
                      )}
                    </td>

                    {/* Total Hours */}
                    <td className="px-4 py-3.5 text-center font-mono">
                      {item.total_hours != null ? (
                        <span className={cn(
                          "px-2.5 py-1 rounded-lg text-xs font-bold",
                          item.total_hours >= 7.5
                            ? "bg-emerald-100 text-emerald-800"
                            : item.total_hours >= 4
                            ? "bg-amber-100 text-amber-800"
                            : "bg-rose-100 text-rose-800"
                        )}>
                          {item.total_hours.toFixed(2)} hrs
                        </span>
                      ) : isAbsent ? (
                        <span className="text-xs text-rose-500 font-semibold">0.00 hrs</span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>

                    {/* Camera */}
                    <td className="px-4 py-3.5 text-xs text-slate-600 font-mono">
                      {item.check_in_camera ? (
                        <span className="px-2 py-0.5 bg-slate-100 rounded border border-slate-200 font-semibold">
                          {item.check_in_camera.split('/').pop()?.slice(0, 12) || item.check_in_camera}
                        </span>
                      ) : (
                        <span className="text-slate-400 italic">No capture</span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3.5 text-right">
                      <button
                        onClick={e => {
                          e.stopPropagation()
                          setSelectedPerson(item)
                        }}
                        className="p-1.5 rounded-lg bg-slate-100 hover:bg-blue-600 hover:text-white text-slate-600 transition-all cursor-pointer shadow-2xs"
                        title="View Full Profile & Attendance Detail"
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
                      <div className="font-bold text-slate-700">No records found for this category</div>
                      <div className="text-xs text-slate-400 max-w-sm">
                        No employees or contractors match the selected filter or search term.
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Person Detail Drawer Modal */}
      {selectedPerson && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-6 bg-gradient-to-r from-blue-600 to-indigo-700 text-white flex items-start justify-between">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-white/20 border-2 border-white/40 overflow-hidden shrink-0 flex items-center justify-center shadow-md">
                  {selectedPerson.photo ? (
                    <img
                      src={selectedPerson.photo.startsWith('/') ? selectedPerson.photo : `/${selectedPerson.photo}`}
                      alt={selectedPerson.name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <span className="text-2xl font-black text-white">
                      {selectedPerson.name.slice(0, 2).toUpperCase()}
                    </span>
                  )}
                </div>
                <div>
                  <h3 className="text-xl font-black text-white leading-tight">{selectedPerson.name}</h3>
                  <div className="text-xs font-mono text-blue-100 font-bold mt-0.5">
                    {selectedPerson.person_code || selectedPerson.person_id}
                  </div>
                  <div className="inline-block mt-1 px-2 py-0.5 rounded bg-white/20 text-white text-[10px] font-black uppercase tracking-wider">
                    {selectedPerson.person_type}
                  </div>
                </div>
              </div>
              <button
                onClick={() => setSelectedPerson(null)}
                className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-all cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200">
                <div>
                  <div className="text-[10px] uppercase font-bold text-slate-500">Department</div>
                  <div className="text-sm font-bold text-slate-800">{selectedPerson.department || 'General'}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase font-bold text-slate-500">Contractor / Firm</div>
                  <div className="text-sm font-bold text-slate-800">{selectedPerson.company || 'Direct'}</div>
                </div>
                {selectedPerson.phone && (
                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-500">Phone Number</div>
                    <div className="text-xs font-semibold text-slate-700 flex items-center gap-1 mt-0.5">
                      <Phone className="w-3.5 h-3.5 text-blue-600" /> {selectedPerson.phone}
                    </div>
                  </div>
                )}
                {selectedPerson.email && (
                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-500">Email Address</div>
                    <div className="text-xs font-semibold text-slate-700 flex items-center gap-1 mt-0.5">
                      <Mail className="w-3.5 h-3.5 text-blue-600" /> {selectedPerson.email}
                    </div>
                  </div>
                )}
              </div>

              {/* Attendance Breakdown */}
              <div className="border border-slate-200 rounded-xl p-4 bg-white shadow-2xs space-y-3">
                <h4 className="text-xs uppercase font-bold tracking-wider text-slate-600 flex items-center gap-2">
                  <Clock className="w-4 h-4 text-blue-600" /> Today's Attendance Timeline
                </h4>

                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-200">
                    <div className="text-[10px] uppercase font-bold text-emerald-700">Check-In</div>
                    <div className="text-sm font-black text-emerald-900 mt-1">{timeOf(selectedPerson.check_in_time)}</div>
                  </div>
                  <div className="p-3 bg-amber-50 rounded-lg border border-amber-200">
                    <div className="text-[10px] uppercase font-bold text-amber-700">Check-Out</div>
                    <div className="text-sm font-black text-amber-900 mt-1">{timeOf(selectedPerson.check_out_time)}</div>
                  </div>
                  <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                    <div className="text-[10px] uppercase font-bold text-blue-700">Total Hours</div>
                    <div className="text-sm font-black text-blue-900 mt-1">
                      {selectedPerson.total_hours != null ? `${selectedPerson.total_hours.toFixed(2)}h` : '0.00h'}
                    </div>
                  </div>
                </div>

                {selectedPerson.status === 'EARLY_EXIT' && (
                  <div className="p-3 bg-amber-50 border border-amber-300 rounded-lg text-xs text-amber-900 font-medium flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                    <strong>Early Departure Alert:</strong> Worker departed early before completing 7.5+ shift hours.
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end">
              <button
                onClick={() => setSelectedPerson(null)}
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

