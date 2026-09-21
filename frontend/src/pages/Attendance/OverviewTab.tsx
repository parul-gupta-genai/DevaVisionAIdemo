import React, { useEffect, useState } from 'react'
import { BadgeCheck, Users, Clock, AlertTriangle, LogIn, LogOut, Calendar, ShieldCheck, UserCheck, UserX } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/utils'
import { api } from '@/api/api'
import { useCameraStateStore } from '@/store/useCameraStateStore'
import AttendanceTable, { type AttendanceItem } from './components/AttendanceTable'

export default function OverviewTab() {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10))
  const [stats, setStats] = useState<any>({})
  const [presentRows, setPresentRows] = useState<AttendanceItem[]>([])
  const [absentRows, setAbsentRows] = useState<AttendanceItem[]>([])
  const [allPersons, setAllPersons] = useState<AttendanceItem[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const states = useCameraStateStore(state => state.states)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const [statsRes, sumRes, absRes, perRes] = await Promise.all([
          api.get('/api/attendance/stats').catch(() => ({ data: {} })),
          api.get('/api/face/attendance/summary', { params: { day } }).catch(() => ({ data: {} })),
          api.get('/api/face/attendance/absentees', { params: { day } }).catch(() => ({ data: {} })),
          api.get('/api/face/persons', { params: { limit: 500 } }).catch(() => ({ data: {} })),
        ])

        if (statsRes.data?.current) {
          setStats(statsRes.data.current)
        }
        setSummary(sumRes.data || {})
        setPresentRows(sumRes.data?.rows || [])
        setAbsentRows(absRes.data?.items || [])
        setAllPersons(perRes.data?.items || [])
      } catch (err) {
        console.error("Failed to fetch attendance overview data", err)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [day])

  useEffect(() => {
    if (states) {
      setStats((prevStats: any) => {
        const newStats = { ...prevStats }
        Object.values(states || {}).forEach((state: any) => {
          const camId = state.camera_id
          if (!newStats[camId]) {
            newStats[camId] = { attendance_logs: [] }
          }

          const evts = state.events?.AttendanceDetectionPlugin || []
          let auth: any[] = []
          let unauthCount = 0
          let liveLogs: any[] | null = null

          evts.forEach((e: any) => {
            if (e.event_type === 'ATTENDANCE_STATE') {
              auth = e.metadata?.authorized_employees_in_frame || []
              unauthCount = e.metadata?.unauthorized_count || 0
              if (Array.isArray(e.metadata?.attendance_logs)) {
                liveLogs = e.metadata.attendance_logs
              }
            }
          })

          newStats[camId].authorized_employees_in_frame = auth
          newStats[camId].unauthorized_count = unauthCount
          if (liveLogs !== null) {
            newStats[camId].attendance_logs = liveLogs
          }
        })
        return newStats
      })
    }
  }, [states])

  const cameraKeys = Object.keys(stats)

  return (
    <div className="space-y-6 text-slate-900">
      {/* Top Site Header */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-emerald-100 text-emerald-800">
            <BadgeCheck className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-900">Site Attendance Overview & All Attendees</h2>
            <p className="text-xs text-slate-500">Live consolidated presence tracking for all employees, contractors, staff, and visitors.</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 shadow-2xs">
            <Calendar className="w-3.5 h-3.5 text-slate-500" />
            <input
              type="date"
              value={day}
              max={new Date().toISOString().slice(0, 10)}
              onChange={e => setDay(e.target.value)}
              className="bg-transparent border-none text-slate-900 font-bold focus:outline-none cursor-pointer"
            />
          </div>
        </div>
      </div>

      {/* Complete Attendance Table Across All Categories */}
      <AttendanceTable
        presentRows={presentRows}
        absentRows={absentRows}
        allPersons={allPersons}
        loading={loading}
      />

      {/* Live Camera Zone Check-ins */}
      {cameraKeys.length > 0 && (
        <div className="space-y-4 pt-2">
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Clock className="w-5 h-5 text-blue-600" /> Live Camera Check-in Zones & Events
          </h3>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
            {cameraKeys.map((camId, i) => {
              const data = stats[camId]

              return (
                <motion.div
                  key={camId}
                  initial={{ opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.1 }}
                  className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs flex flex-col group"
                >
                  <div className="p-5 bg-gradient-to-r from-emerald-500/10 to-transparent border-b border-slate-200">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2.5">
                        <div className="p-2 bg-emerald-100 rounded-lg text-emerald-700">
                          <BadgeCheck className="w-4 h-4" />
                        </div>
                        <h4 className="text-base font-bold text-slate-900">Zone Check-in</h4>
                      </div>
                      <span className="text-xs text-slate-500 font-mono bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                        {camId.split('/').pop() || camId}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-4 mt-4">
                      <div className="flex flex-col">
                        <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Authorized Visible</span>
                        <div className="flex items-end gap-2 mt-0.5">
                          <span className="text-2xl font-black text-slate-900">{data.authorized_employees_in_frame?.length || 0}</span>
                          <Users className="w-4 h-4 text-emerald-600 mb-0.5" />
                        </div>
                      </div>

                      <div className="flex flex-col">
                        <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Unauthorized Detected</span>
                        <div className="flex items-end gap-2 mt-0.5">
                          <span className="text-2xl font-black text-slate-900">{data.unauthorized_count || 0}</span>
                          <AlertTriangle className={cn("w-4 h-4 mb-0.5", data.unauthorized_count > 0 ? "text-rose-600" : "text-slate-400")} />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="p-5">
                    <h5 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5" /> Recent Action Logs
                    </h5>

                    {(!data.attendance_logs || data.attendance_logs.length === 0) ? (
                      <div className="text-center py-5 text-xs text-slate-400">
                        No live camera check-ins detected in the last few minutes.
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {data.attendance_logs.slice().reverse().map((log: any, idx: number) => {
                          const isCheckIn = log.action === 'CHECK IN'
                          return (
                            <div key={idx} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                              <div className="flex items-center gap-2.5">
                                <div className={cn("p-1 rounded-full", isCheckIn ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700")}>
                                  {isCheckIn ? <LogIn className="w-3.5 h-3.5" /> : <LogOut className="w-3.5 h-3.5" />}
                                </div>
                                <div>
                                  <span className="font-bold text-xs text-slate-900">{log.employee}</span>
                                  <span className={cn("ml-2 text-[10px] uppercase tracking-wider font-black", isCheckIn ? "text-emerald-700" : "text-amber-700")}>
                                    {log.action}
                                  </span>
                                </div>
                              </div>
                              <span className="text-[11px] text-slate-500 font-mono">
                                {new Date(log.time * 1000).toLocaleTimeString()}
                              </span>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                </motion.div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

