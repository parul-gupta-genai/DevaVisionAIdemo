import React, { useCallback, useEffect, useRef, useState } from 'react'
import { 
  UserPlus, 
  UserX, 
  SlidersHorizontal, 
  Users, 
  LogIn, 
  Clock, 
  Camera, 
  RefreshCw, 
  Upload, 
  CheckCircle2, 
  AlertCircle, 
  X, 
  Loader2, 
  Sparkles,
  Check
} from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/utils'
import { api } from '@/api/api'

import AttendanceTable, { type AttendanceItem } from './components/AttendanceTable'

export default function FaceRecognitionTab() {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10))
  const [summary, setSummary] = useState<any>(null)
  const [absentees, setAbsentees] = useState<any[]>([])
  const [allPersons, setAllPersons] = useState<any[]>([])
  const [tuning, setTuning] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [enrolOpen, setEnrolOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: any = { day }
      const [s, a, p, t] = await Promise.all([
        api.get('/api/face/attendance/summary', { params }),
        api.get('/api/face/attendance/absentees', { params }),
        api.get('/api/face/persons', { params: { limit: 500 } }),
        api.get('/api/face/tuning').catch(() => ({ data: null })),
      ])
      setSummary(s.data)
      setAbsentees(a.data?.items || [])
      setAllPersons(p.data?.items || [])
      setTuning(t.data)
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message || e?.message || 'Failed to load face data')
    } finally {
      setLoading(false)
    }
  }, [day])

  useEffect(() => { load() }, [load])

  return (
    <div className="space-y-6 text-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 tracking-wide">Face Recognition Attendance & Register</h2>
          <p className="text-sm text-slate-500">Live presence tracking, early departures, absentee details, and AI face profiles.</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="date" value={day} max={new Date().toISOString().slice(0, 10)}
            onChange={e => setDay(e.target.value)}
            className="bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary shadow-xs font-medium"
          />
          <button
            onClick={() => setEnrolOpen(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold tracking-wide shadow-md shadow-blue-500/20 transition-all cursor-pointer"
          >
            <UserPlus className="w-4 h-4" /> Enrol Face
          </button>
        </div>
      </div>

      {tuning && !tuning.engine_available && (
        <div className="border border-amber-300 bg-amber-50 rounded-xl p-4 text-sm text-amber-800 font-semibold flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-amber-600 shrink-0" />
          The face recognition engine is not loaded on this server. No new attendance will be recorded via AI.
        </div>
      )}

      {error && (
        <div className="border border-danger/30 bg-danger/10 rounded-xl p-4 text-sm text-danger font-semibold">
          {error}
        </div>
      )}

      {/* Comprehensive Filterable Table & Details */}
      <AttendanceTable
        presentRows={summary?.rows || []}
        absentRows={absentees}
        allPersons={allPersons}
        loading={loading}
        onEnrolClick={() => setEnrolOpen(true)}
      />

      {tuning && (
        <details className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs">
          <summary className="text-sm font-bold text-slate-700 cursor-pointer flex items-center gap-2">
            <SlidersHorizontal className="w-4 h-4 text-blue-600" /> AI Face Recognition Engine Settings
          </summary>
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(tuning.values || {}).map(([k, v]) => (
              <div key={k} className="bg-slate-50 rounded-xl p-3 border border-slate-200">
                <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">{k.replace(/_/g, ' ')}</div>
                <div className="text-lg font-bold text-slate-900 mt-1">{String(v)}</div>
              </div>
            ))}
          </div>
          <div className="mt-4 text-xs text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-200">
            <strong>Check-in cameras:</strong> {tuning.checkin_cameras?.join(', ') || 'Any (All Entrance/Gate Cameras)'} &nbsp;·&nbsp;
            <strong>Check-out cameras:</strong> {tuning.checkout_cameras?.join(', ') || 'Any (Configured Exits)'}
          </div>
        </details>
      )}

      {enrolOpen && <EnrolDialog onClose={() => { setEnrolOpen(false); load() }} />}
    </div>
  )
}

function Stat({ icon: Icon, label, value, tone }: any) {
  return (
    <div className={cn("bg-white border rounded-xl p-5 flex items-center gap-4 shadow-xs", tone)}>
      <div className={cn('p-3 rounded-xl shadow-xs', tone)}>
        <Icon className="w-6 h-6" />
      </div>
      <div>
        <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500 mb-0.5">{label}</div>
        <div className="text-2xl font-black leading-tight text-slate-900">{value}</div>
      </div>
    </div>
  )
}

function EnrolDialog({ onClose }: { onClose: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const [mode, setMode] = useState<'camera' | 'upload'>('camera')
  const [facingMode, setFacingMode] = useState<'user' | 'environment'>('user')
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null)
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [isStartingCamera, setIsStartingCamera] = useState(false)

  const [form, setForm] = useState({
    name: '', person_code: '', person_type: 'EMPLOYEE', department: '', company: '',
  })
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [checkResult, setCheckResult] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: string; text: string } | null>(null)

  // Camera Management
  const stopCamera = useCallback(() => {
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop())
      setMediaStream(null)
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
  }, [mediaStream])

  const startCamera = useCallback(async (currentFacing: 'user' | 'environment' = facingMode) => {
    setIsStartingCamera(true)
    setCameraError(null)

    if (!navigator?.mediaDevices?.getUserMedia) {
      setCameraError("Camera access requires a secure context (HTTPS) or is not supported by this browser.")
      setIsStartingCamera(false)
      return
    }

    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop())
      setMediaStream(null)
    }

    let stream: MediaStream | null = null
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: currentFacing,
          width: { ideal: 640 },
          height: { ideal: 640 }
        },
        audio: false
      })
    } catch (err: any) {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      } catch (fallbackErr: any) {
        setCameraError("Unable to access camera. Please allow camera permissions or upload a photo below.")
      }
    }

    if (stream) {
      setMediaStream(stream)
      setCameraError(null)
    }
    setIsStartingCamera(false)
  }, [facingMode, mediaStream])

  // Attach stream to video element
  useEffect(() => {
    if (mode === 'camera' && !preview) {
      startCamera(facingMode)
    }
    return () => {
      stopCamera()
    }
  }, [mode, facingMode])

  useEffect(() => {
    if (videoRef.current && mediaStream) {
      videoRef.current.srcObject = mediaStream
      videoRef.current.onloadedmetadata = () => {
        videoRef.current?.play().catch(e => console.warn("Play error:", e))
      }
    }
  }, [mediaStream, mode, preview])

  // Capture photo from video stream
  const capturePhoto = () => {
    if (!videoRef.current) return
    const video = videoRef.current
    const canvas = canvasRef.current || document.createElement('canvas')
    canvas.width = video.videoWidth || 640
    canvas.height = video.videoHeight || 640

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // If front camera, mirror horizontally for intuitive natural snap
    if (facingMode === 'user') {
      ctx.translate(canvas.width, 0)
      ctx.scale(-1, 1)
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

    canvas.toBlob(blob => {
      if (!blob) return
      const capturedFile = new File([blob], `face_${Date.now()}.jpg`, { type: 'image/jpeg' })
      setFile(capturedFile)
      setPreview(URL.createObjectURL(blob))
      stopCamera()
      setCheckResult(null)
      setMessage(null)
    }, 'image/jpeg', 0.95)
  }

  const retakePhoto = () => {
    setFile(null)
    setPreview(null)
    setCheckResult(null)
    setMessage(null)
    if (mode === 'camera') {
      startCamera(facingMode)
    }
  }

  const pickFile = (f: File | null) => {
    setFile(f)
    setCheckResult(null)
    setMessage(null)
    setPreview(f ? URL.createObjectURL(f) : null)
  }

  const validate = async () => {
    if (!file) return
    setBusy(true)
    setMessage(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api.post('/api/face/enrol/validate', fd,
        { headers: { 'Content-Type': 'multipart/form-data' } })
      setCheckResult(res.data)
      if (!res.data.acceptable) setMessage({ kind: 'warn', text: res.data.message })
    } catch (e: any) {
      const d = e?.response?.data?.detail
      const msg = typeof d === 'string' ? d : d?.message || 'Photo check failed'
      setMessage({ kind: 'error', text: msg })
    } finally {
      setBusy(false)
    }
  }

  const submit = async () => {
    if (!file || !form.name.trim()) {
      setMessage({ kind: 'error', text: 'Full name and a captured/uploaded photo are required.' })
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      Object.entries(form).forEach(([k, v]) => v && fd.append(k, v))
      await api.post('/api/face/enrol', fd,
        { headers: { 'Content-Type': 'multipart/form-data' } })
      setMessage({ kind: 'ok', text: `✅ ${form.name} successfully enrolled!` })
      setTimeout(() => {
        stopCamera()
        onClose()
      }, 1000)
    } catch (e: any) {
      const d = e?.response?.data?.detail
      const msg = typeof d === 'string' ? d : d?.message || 'Enrolment failed. Please try again.'
      setMessage({ kind: 'error', text: msg })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4"
         onClick={() => { stopCamera(); onClose() }}>
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        onClick={e => e.stopPropagation()}
        className="bg-white border border-slate-200 shadow-2xl rounded-2xl p-6 sm:p-7 w-full max-w-xl space-y-5 text-slate-900 max-h-[92vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-blue-50 text-blue-600 border border-blue-200">
              <Camera className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-900">Live Face Enrolment</h3>
              <p className="text-xs text-slate-500">Capture face photo or upload for AI attendance tracking</p>
            </div>
          </div>
          <button onClick={() => { stopCamera(); onClose() }} className="text-slate-400 hover:text-slate-700 p-1 rounded-md cursor-pointer">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Capture Mode Toggle */}
        <div className="flex rounded-xl bg-slate-100 p-1 border border-slate-200">
          <button
            type="button"
            onClick={() => { setMode('camera'); retakePhoto() }}
            className={cn(
              "flex-1 py-1.5 text-xs font-bold rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer",
              mode === 'camera' ? "bg-white text-blue-600 shadow-xs" : "text-slate-600 hover:text-slate-900"
            )}
          >
            <Camera className="w-4 h-4" /> Live Camera
          </button>
          <button
            type="button"
            onClick={() => { setMode('upload'); stopCamera() }}
            className={cn(
              "flex-1 py-1.5 text-xs font-bold rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer",
              mode === 'upload' ? "bg-white text-blue-600 shadow-xs" : "text-slate-600 hover:text-slate-900"
            )}
          >
            <Upload className="w-4 h-4" /> File Upload
          </button>
        </div>

        {/* Camera / Photo Area */}
        <div className="space-y-2">
          {mode === 'camera' ? (
            <div className="relative w-full h-64 sm:h-72 bg-slate-900 rounded-2xl overflow-hidden flex items-center justify-center shadow-inner border border-slate-200">
              {preview ? (
                <div className="relative w-full h-full">
                  <img src={preview} alt="Captured preview" className="w-full h-full object-cover" />
                  <button
                    type="button"
                    onClick={retakePhoto}
                    className="absolute bottom-3 right-3 px-3 py-1.5 bg-slate-900/80 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 backdrop-blur-xs transition-colors cursor-pointer"
                  >
                    <RefreshCw className="w-3.5 h-3.5" /> Retake
                  </button>
                </div>
              ) : cameraError ? (
                <div className="p-6 text-center text-rose-300 space-y-3">
                  <AlertCircle className="w-8 h-8 mx-auto text-rose-400" />
                  <p className="text-xs">{cameraError}</p>
                  <button
                    type="button"
                    onClick={() => startCamera(facingMode)}
                    className="px-4 py-2 bg-white/20 hover:bg-white/30 text-white rounded-lg text-xs font-semibold"
                  >
                    Retry Camera
                  </button>
                </div>
              ) : (
                <div className="relative w-full h-full flex items-center justify-center">
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className={cn(
                      "w-full h-full object-cover",
                      facingMode === 'user' && "-scale-x-100"
                    )}
                  />
                  
                  {/* Face Positioning Guide Outline */}
                  <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                    <div className="w-44 h-56 rounded-full border-2 border-dashed border-blue-400/80 shadow-2xl flex items-center justify-center">
                      <span className="text-[10px] font-bold text-blue-200 bg-slate-900/60 px-2.5 py-0.5 rounded-full backdrop-blur-xs">
                        Align Face Here
                      </span>
                    </div>
                  </div>

                  {/* Switch Camera Button (Mobile/Multi-Cam) */}
                  <button
                    type="button"
                    onClick={() => {
                      const next = facingMode === 'user' ? 'environment' : 'user'
                      setFacingMode(next)
                    }}
                    className="absolute top-3 right-3 p-2 bg-slate-900/60 hover:bg-slate-900 text-white rounded-full backdrop-blur-xs transition-colors cursor-pointer"
                    title="Switch Camera"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>

                  {/* Capture Button */}
                  <button
                    type="button"
                    onClick={capturePhoto}
                    disabled={isStartingCamera || !mediaStream}
                    className="absolute bottom-4 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 active:scale-95 text-white font-bold text-xs rounded-full shadow-lg shadow-blue-500/40 flex items-center gap-2 transition-all cursor-pointer disabled:opacity-50"
                  >
                    <Camera className="w-4 h-4" /> Capture Photo
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div
              onClick={() => fileRef.current?.click()}
              className="w-full h-44 rounded-2xl border-2 border-dashed border-blue-300 bg-blue-50/50 hover:bg-blue-50 transition-colors flex flex-col items-center justify-center cursor-pointer overflow-hidden p-4"
            >
              {preview ? (
                <div className="relative w-full h-full flex items-center justify-center">
                  <img src={preview} alt="Upload preview" className="max-h-full rounded-xl object-cover" />
                  <span className="absolute bottom-2 bg-slate-900/70 text-white text-[10px] px-2.5 py-1 rounded-full">
                    Click to replace
                  </span>
                </div>
              ) : (
                <div className="text-center space-y-1.5">
                  <Upload className="w-8 h-8 text-blue-600 mx-auto" />
                  <div className="text-sm font-semibold text-slate-900">Click to upload photo</div>
                  <div className="text-xs text-slate-500">Supports JPG, PNG, WEBP (Max 10MB)</div>
                </div>
              )}
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={e => pickFile(e.target.files?.[0] || null)}
              />
            </div>
          )}
        </div>

        {/* User Details Form */}
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Full Name *</label>
              <input
                placeholder="e.g. Rajesh Kumar"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-sm text-slate-900 focus:ring-2 focus:ring-primary/40 focus:border-primary outline-none"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Person / Employee Code</label>
              <input
                placeholder="e.g. EMP-1042"
                value={form.person_code}
                onChange={e => setForm({ ...form, person_code: e.target.value })}
                className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-sm text-slate-900 focus:ring-2 focus:ring-primary/40 focus:border-primary outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Person Type</label>
              <select
                value={form.person_type}
                onChange={e => setForm({ ...form, person_type: e.target.value })}
                className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3 py-2 text-sm text-slate-900 focus:ring-2 focus:ring-primary/40 focus:border-primary outline-none"
              >
                <option value="EMPLOYEE">Employee</option>
                <option value="CONTRACTOR">Contractor</option>
                <option value="VENDOR">Vendor</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Department</label>
              <input
                placeholder="e.g. Civil / MEP"
                value={form.department}
                onChange={e => setForm({ ...form, department: e.target.value })}
                className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-sm text-slate-900 focus:ring-2 focus:ring-primary/40 focus:border-primary outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Company / Subcontractor</label>
              <input
                placeholder="e.g. Hero Homes"
                value={form.company}
                onChange={e => setForm({ ...form, company: e.target.value })}
                className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-sm text-slate-900 focus:ring-2 focus:ring-primary/40 focus:border-primary outline-none"
              />
            </div>
          </div>
        </div>

        {/* Validation result */}
        {checkResult && (
          <div className={cn('rounded-xl p-3.5 text-xs font-medium border',
            checkResult.acceptable ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-amber-50 text-amber-800 border-amber-200')}>
            <div className="flex items-center gap-1.5 font-bold">
              {checkResult.acceptable ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <AlertCircle className="w-4 h-4 text-amber-600" />}
              {checkResult.message}
            </div>
            {checkResult.face && (
              <div className="mt-1.5 pt-1.5 border-t border-[currentColor]/15 opacity-90 font-mono text-[11px] flex gap-3">
                <span>Face Size: {checkResult.face.width}×{checkResult.face.height}px</span>
                <span>Quality: {checkResult.face.det_score}</span>
                <span>Sharpness: {checkResult.face.sharpness}</span>
              </div>
            )}
          </div>
        )}

        {message && (
          <div className={cn('rounded-xl p-3 text-xs font-semibold text-center border',
            message.kind === 'ok' ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : message.kind === 'warn' ? 'bg-amber-50 text-amber-800 border-amber-200'
                : 'bg-rose-50 text-rose-800 border-rose-200')}>
            {message.text}
          </div>
        )}

        <div className="flex justify-end gap-2.5 pt-2 border-t border-slate-100">
          <button
            type="button"
            onClick={() => { stopCamera(); onClose() }}
            className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-sm font-semibold text-slate-700 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={validate}
            disabled={!file || busy}
            className="px-4 py-2 rounded-xl bg-blue-50 text-blue-600 hover:bg-blue-100 text-sm font-semibold border border-blue-200 disabled:opacity-40 transition-colors cursor-pointer"
          >
            Check Quality
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy || !file || !form.name.trim()}
            className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 active:scale-95 text-sm font-bold text-white shadow-md shadow-blue-500/20 disabled:opacity-40 transition-all flex items-center gap-1.5 cursor-pointer"
          >
            {busy ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> Enrolling…
              </>
            ) : (
              <>
                <UserPlus className="w-4 h-4" /> Enrol Face
              </>
            )}
          </button>
        </div>
      </motion.div>
    </div>
  )
}
