import React, { useState, useEffect } from 'react'
import { api } from '@/api/api'
import AttendanceTable, { type AttendanceItem } from './components/AttendanceTable'
import { Users, Calendar } from 'lucide-react'

export default function EmployeesTab() {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10))
  const [presentRows, setPresentRows] = useState<AttendanceItem[]>([])
  const [absentRows, setAbsentRows] = useState<AttendanceItem[]>([])
  const [allPersons, setAllPersons] = useState<AttendanceItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [sumRes, absRes, perRes] = await Promise.all([
          api.get('/api/face/attendance/summary', { params: { day, person_type: 'EMPLOYEE' } }),
          api.get('/api/face/attendance/absentees', { params: { day, person_type: 'EMPLOYEE' } }),
          api.get('/api/face/persons', { params: { person_type: 'EMPLOYEE', limit: 500 } }),
        ])
        setPresentRows(sumRes.data?.rows || [])
        setAbsentRows(absRes.data?.items || [])
        setAllPersons(perRes.data?.items || [])
      } catch (e) {
        console.error("Failed to load employee attendance:", e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [day])

  return (
    <div className="space-y-4 text-slate-900">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-blue-100 text-blue-800">
            <Users className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-900">Company Employees Attendance</h2>
            <p className="text-xs text-slate-500">Full employee register, live presence, early departures, and absentees.</p>
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

      <AttendanceTable
        presentRows={presentRows}
        absentRows={absentRows}
        allPersons={allPersons}
        loading={loading}
      />
    </div>
  )
}

