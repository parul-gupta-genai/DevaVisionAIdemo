import { Maximize, Camera as CameraIcon, Video, VideoOff, Crosshair, Mic, Volume2, Settings, PictureInPicture, Signal, Users, SlidersHorizontal, Check, Play, Square, Zap, Box, Trash2, UserCheck, Pencil, Shapes } from 'lucide-react'
import { memo, useEffect, useState, useRef } from 'react'
import { cn } from '@/utils/utils'
import { motion } from 'framer-motion'
import { VideoPlayer } from './VideoPlaceholder'
import { AnalyticsOverlay } from './AnalyticsOverlay'
import { useAppStore } from '@/store/useAppStore'
import { useToastStore } from '@/store/useToastStore'
import { useCameraStateStore } from '@/store/useCameraStateStore'
import { api } from '@/api/api'
import { webrtcStreamManager } from '@/services/webrtcStreamManager'

import { PluginManagerModal } from './PluginManagerModal'
import { CountingLineEditor } from './CountingLineEditor'
import { RestrictedZoneEditor } from './RestrictedZoneEditor'

export const CameraCard = memo(({ id, name, location, pipelineStatus: parentPipelineStatus = "Stopped", onEdit }: any) => {
  const { activeCameraId, setActiveCamera } = useAppStore()
  const { addToast } = useToastStore()
  const countingEvents = useCameraStateStore(state => state.states[id]?.events?.PeopleCountingPlugin)
  const cartonEvents = useCameraStateStore(state => state.states[id]?.events?.CartonCountingPlugin)

  let personCount = 0
  let inCount = 0
  let outCount = 0
  let totalPeopleCount = 0
  let isCountingEnabled = false

  if (Array.isArray(countingEvents)) {
    for (const event of countingEvents) {
      if (event.event_type === "PERSON_COUNT") {
        personCount = event.metadata?.current_people_in_frame || 0
        inCount = event.metadata?.in_count || 0
        outCount = event.metadata?.out_count || 0
        totalPeopleCount = event.metadata?.total_unique_people_seen || 0
        isCountingEnabled = true
        break
      }
    }
  }

  let cartonCount = 0
  if (Array.isArray(cartonEvents)) {
    for (const event of cartonEvents) {
      if (event.event_type === "CARTON_STATS") {
        cartonCount = event.metadata?.total_cartons_counted || 0
        break
      }
    }
  }
  const isActive = activeCameraId === id;
  const [pipelineStatus, setPipelineStatus] = useState<string>(parentPipelineStatus)
  const [isPluginModalOpen, setIsPluginModalOpen] = useState(false)
  const [isLineEditorOpen, setIsLineEditorOpen] = useState(false)
  const [isZoneEditorOpen, setIsZoneEditorOpen] = useState(false)
  const [isToggling, setIsToggling] = useState(false)
  const [lastToggleTime, setLastToggleTime] = useState<number>(0)
  
  const [selectedRes, setSelectedRes] = useState<string>(() => {
    try { return localStorage.getItem(`camera_res_${id}`) || '1080p' } catch { return '1080p' }
  })
  const [selectedBitrate, setSelectedBitrate] = useState<string>(() => {
    try { return localStorage.getItem(`camera_bitrate_${id}`) || '4.2M' } catch { return '4.2M' }
  })
  const [isResMenuOpen, setIsResMenuOpen] = useState(false)
  const [isBitrateMenuOpen, setIsBitrateMenuOpen] = useState(false)

  const handleSelectRes = (res: string) => {
    setSelectedRes(res)
    try { localStorage.setItem(`camera_res_${id}`, res) } catch {}
    setIsResMenuOpen(false)
    addToast({ title: 'Resolution Changed', message: `${name}: Stream resolution set to ${res}`, type: 'success' })
  }

  const handleSelectBitrate = (br: string) => {
    setSelectedBitrate(br)
    try { localStorage.setItem(`camera_bitrate_${id}`, br) } catch {}
    setIsBitrateMenuOpen(false)
    addToast({ title: 'Bitrate Changed', message: `${name}: Bitrate set to ${br}`, type: 'success' })
  }

  const telemetry = useCameraStateStore(state => state.states[id])
  const fps = telemetry?.fps || 0
  const latency = telemetry?.latency_ms || 0

  const [isVisible, setIsVisible] = useState(false)
  const cardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsVisible(entry.isIntersecting)
      },
      { threshold: 0.1 }
    )
    if (cardRef.current) {
      observer.observe(cardRef.current)
    }
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    // Sync from parent polling, but ignore it for 8 seconds after a toggle
    // to prevent reverting to a stale state before the next poll completes.
    if (!isToggling && Date.now() - lastToggleTime > 8000) {
      setPipelineStatus(parentPipelineStatus)
    }
  }, [parentPipelineStatus, isToggling, lastToggleTime])

  useEffect(() => {
    // The editor overlay is gated on a running pipeline; without this reset a
    // click while stopped leaves the flag set and the full-card editor pops
    // open uninvited the moment the pipeline is started.
    if (pipelineStatus === 'Stopped') {
      setIsLineEditorOpen(false)
      setIsZoneEditorOpen(false)
    }
  }, [pipelineStatus])

  const togglePipeline = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isToggling) return // Prevent double-clicks
    setIsToggling(true)
    const isStopping = pipelineStatus !== "Stopped"
    const endpoint = isStopping ? "/api/cameras/stop" : "/api/cameras/start"
    const newStatus = isStopping ? "Stopped" : "Connected"
    
    if (isStopping) {
      webrtcStreamManager.closeStream(id)
    }

    try {
      setPipelineStatus(newStatus)
      setLastToggleTime(Date.now())
      await api.post(endpoint, { camera_id: id })
      addToast({
        title: "Success",
        message: `Camera ${isStopping ? 'stopped' : 'started'}.`,
        type: "success"
      })
    } catch (err: any) {
      // Revert if failed
      setPipelineStatus(pipelineStatus)
      addToast({
        title: "Error",
        message: err.response?.data?.detail || "Action failed.",
        type: "danger"
      })
    } finally {
      setIsToggling(false)
    }
  }

  return (
    <div 
      ref={cardRef}
      className={cn(
        "w-full h-full relative group overflow-hidden rounded-2xl transition-all duration-500",
        isActive ? "ring-2 ring-primary glow-primary border-transparent glass-pro shadow-[0_0_40px_rgba(0,112,243,0.3)]" : "glass hover-lift border border-foreground/5 hover:border-foreground/20"
      )}
      onClick={() => setActiveCamera(isActive ? null : id)}
    >
      {/* Top Overlay */}
      <div className="absolute top-0 inset-x-0 p-4 bg-gradient-to-b from-black/80 via-black/40 to-transparent z-30 flex justify-between items-start pointer-events-none transition-opacity duration-300">
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1.5">
            <span className="font-bold text-sm text-white drop-shadow-lg flex items-center gap-2 tracking-wide">
              {name}
              <span className="text-[10px] bg-foreground/10 px-2 py-0.5 rounded text-foreground/70 uppercase tracking-widest">{location}</span>
            </span>
            <div className="flex gap-2">
              <span className="flex items-center gap-1.5 text-[10px] bg-danger/20 text-danger border border-danger/30 px-2 py-0.5 rounded shadow-sm uppercase font-black tracking-widest">
                <span className="w-1.5 h-1.5 rounded-full bg-danger animate-pulse glow-danger" /> 
                LIVE {fps > 0 ? fps : '--'} FPS
              </span>
              <span className="flex items-center gap-1.5 text-[10px] bg-accent/20 text-accent border border-accent/30 px-2 py-0.5 rounded shadow-sm uppercase font-black tracking-widest glow-accent">
                AI ACTIVE
              </span>
            </div>
          </div>

          {/* Conditional Check In / Check Out Buttons */}
          {isActive && (
            <motion.div 
              initial={{ opacity: 0, y: -10 }} 
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-1.5 mt-1 pointer-events-auto"
            >
              <button 
                onClick={(e) => { 
                  e.stopPropagation();
                  api.post('/events/manual', { camera_id: id, event_type: 'info', description: `Manual check-in recorded for ${name}` })
                  addToast({ title: 'Checked In', message: `Manual check-in recorded for ${name}`, type: 'success', cameraName: name })
                }}
                className="px-2 py-1 bg-success/90 hover:bg-success text-success-foreground text-[10px] font-bold rounded shadow-sm transition-colors border border-success/50"
                title="Check In"
              >
                CI
              </button>
              <button 
                onClick={(e) => { 
                  e.stopPropagation();
                  api.post('/events/manual', { camera_id: id, event_type: 'warning', description: `Manual check-out recorded for ${name}` })
                  addToast({ title: 'Checked Out', message: `Manual check-out recorded for ${name}`, type: 'warning', cameraName: name })
                }}
                className="px-2 py-1 bg-danger/90 hover:bg-danger text-danger-foreground text-[10px] font-bold rounded shadow-sm transition-colors border border-danger/50"
                title="Check Out"
              >
                CO
              </button>
            </motion.div>
          )}
        </div>
        
        {/* Top Right: Controls & Info */}
        <div className="flex flex-col items-end gap-1.5 pointer-events-none">
          <div className="flex items-center gap-1.5 pointer-events-auto">
            <button 
              onClick={togglePipeline}
              disabled={isToggling}
              className={cn(
                "p-1.5 rounded backdrop-blur border border-foreground/10 transition-colors flex items-center gap-1 text-[10px] font-bold shadow-md",
                isToggling ? "bg-foreground/30 text-white/50 cursor-wait" :
                pipelineStatus === "Stopped" ? "bg-success/80 hover:bg-success text-white" : "bg-danger/80 hover:bg-danger text-white"
              )}
              title={isToggling ? 'Processing...' : pipelineStatus === "Stopped" ? 'Start Pipeline' : 'Stop Pipeline'}
            >
              {isToggling ? (
                <><div className="w-3 h-3 border-2 border-white/50 border-t-white rounded-full animate-spin" /> WAIT</>
              ) : pipelineStatus === "Stopped" ? (
                <><Play className="w-3 h-3 fill-current" /> START</>
              ) : (
                <><Square className="w-3 h-3 fill-current" /> STOP</>
              )}
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setIsPluginModalOpen(true); }}
              className="px-2 py-1.5 bg-primary/20 hover:bg-primary/40 text-primary border border-primary/30 rounded backdrop-blur transition-colors flex items-center gap-1.5 text-[10px] font-bold shadow-[0_0_10px_rgba(0,112,243,0.2)] uppercase tracking-widest pointer-events-auto"
              title="Manage Analytics Plugins"
            >
              <Zap className="w-3 h-3 fill-current" />
              Analytics
            </button>
            {pipelineStatus !== 'Stopped' && (
              <button
                onClick={(e) => { e.stopPropagation(); setIsZoneEditorOpen(true); }}
                className="px-2 py-1.5 bg-amber-500/20 hover:bg-amber-500/40 text-amber-300 border border-amber-500/30 rounded backdrop-blur transition-colors flex items-center gap-1.5 text-[10px] font-bold shadow-[0_0_10px_rgba(245,158,11,0.2)] uppercase tracking-widest pointer-events-auto"
                title="Draw restricted zones on the live video"
              >
                <Shapes className="w-3 h-3" />
                Zones
              </button>
            )}
            {isCountingEnabled && pipelineStatus !== 'Stopped' && (
              <button
                onClick={(e) => { e.stopPropagation(); setIsLineEditorOpen(true); }}
                className="px-2 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/40 text-cyan-300 border border-cyan-500/30 rounded backdrop-blur transition-colors flex items-center gap-1.5 text-[10px] font-bold shadow-[0_0_10px_rgba(34,211,238,0.2)] uppercase tracking-widest pointer-events-auto"
                title="Draw people counting lines on the live video"
              >
                <Crosshair className="w-3 h-3" />
                Lines
              </button>
            )}
            {onEdit && (
              <button
                onClick={(e) => { e.stopPropagation(); onEdit(); }}
                className="p-1.5 bg-warning/20 hover:bg-warning/80 text-warning hover:text-white border border-warning/30 rounded backdrop-blur transition-colors flex items-center gap-1 text-[10px] font-bold shadow-md pointer-events-auto"
                title="Edit Camera (name / video / RTSP source)"
              >
                <Pencil className="w-3 h-3" /> EDIT
              </button>
            )}
            <button
              onClick={async (e) => {
                e.stopPropagation();
                if (confirm('Are you sure you want to delete this camera?')) {
                  try {
                    await api.delete(`/api/cameras/${id}`);
                    addToast({ title: 'Deleted', message: 'Camera removed successfully.', type: 'success' });
                    window.location.reload();
                  } catch (err) {
                    addToast({ title: 'Error', message: 'Failed to delete camera.', type: 'danger' });
                  }
                }
              }}
              className="p-1.5 bg-danger/20 hover:bg-danger/80 text-danger hover:text-white border border-danger/30 rounded backdrop-blur transition-colors flex items-center gap-1 text-[10px] font-bold shadow-md pointer-events-auto"
              title="Delete Camera"
            >
              <Trash2 className="w-3 h-3" /> DEL
            </button>
            {isCountingEnabled && (
              <>
                <div className="flex items-center gap-1.5 text-[10px] bg-background/60 border border-foreground/10 px-2 py-1 rounded backdrop-blur-sm text-white font-mono shadow-md pointer-events-auto" title="Current People in Frame">
                  <Users className="w-3 h-3 text-primary" />
                  <span className="font-semibold text-gray-300">CW:</span>
                  <span className={cn(
                    "font-bold",
                    personCount > 10 ? "text-danger" : personCount > 5 ? "text-warning" : "text-success"
                  )}>
                    {personCount}
                  </span>
                </div>

                <div className="flex items-center gap-1.5 text-[10px] bg-background/60 border border-cyan-500/30 px-2 py-1 rounded backdrop-blur-sm text-white font-mono shadow-md pointer-events-auto" title="Footfall Entry Count (IN)">
                  <span className="w-2 h-2 rounded-full bg-cyan-400" />
                  <span className="font-semibold text-gray-300">IN:</span>
                  <span className="font-bold text-cyan-400">
                    {inCount}
                  </span>
                </div>

                {outCount > 0 && (
                  <div className="flex items-center gap-1.5 text-[10px] bg-background/60 border border-pink-500/30 px-2 py-1 rounded backdrop-blur-sm text-white font-mono shadow-md pointer-events-auto" title="Footfall Exit Count (OUT)">
                    <span className="w-2 h-2 rounded-full bg-pink-400" />
                    <span className="font-semibold text-gray-300">OUT:</span>
                    <span className="font-bold text-pink-400">
                      {outCount}
                    </span>
                  </div>
                )}

                <div className="flex items-center gap-1.5 text-[10px] bg-background/60 border border-emerald-500/30 px-2 py-1 rounded backdrop-blur-sm text-white font-mono shadow-md pointer-events-auto" title="Total Unique People Counted">
                  <UserCheck className="w-3 h-3 text-emerald-400" />
                  <span className="font-semibold text-gray-300">TOT:</span>
                  <span className="font-bold text-emerald-400">
                    {totalPeopleCount}
                  </span>
                </div>
              </>
            )}
            
            {cartonCount > 0 && (
              <div className="flex items-center gap-1.5 text-[10px] bg-background/60 border border-foreground/10 px-2 py-1 rounded backdrop-blur-sm text-white font-mono shadow-md pointer-events-auto">
                <Box className="w-3 h-3 text-orange-500" />
                <span className="font-semibold text-gray-300">BOX:</span>
                <span className="font-bold text-orange-400">
                  {cartonCount}
                </span>
              </div>
            )}
            
            <Signal className="w-4 h-4 text-success drop-shadow-md" />
          </div>
        </div>
      </div>

      {/* Video Content */}
      <div className="relative w-full h-full overflow-hidden">
        {pipelineStatus !== 'Stopped' ? (
          isVisible ? (
            <>
              <VideoPlayer cameraId={id} streamUrl="mock" poster="https://images.unsplash.com/photo-1557597774-9d273605dfa9?w=800&q=80" />
              <AnalyticsOverlay cameraId={id} />
            </>
          ) : (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black text-foreground/30">
              <VideoOff className="w-8 h-8 mb-2 opacity-50" />
              <span className="font-mono text-xs tracking-widest">STANDBY (OFF-SCREEN)</span>
            </div>
          )
        ) : (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-background/90 text-foreground/50">
            <VideoOff className="w-12 h-12 mb-4 opacity-50" />
            <span className="font-mono text-sm tracking-widest">CAMERA STOPPED</span>
          </div>
        )}
      </div>

      {/* Bottom Overlay - Telemetry HUD */}
      <div className="absolute bottom-0 inset-x-0 p-4 bg-gradient-to-t from-black/90 via-black/50 to-transparent z-10 flex justify-between items-end pointer-events-none">
        <div className="flex gap-4 text-[10px] text-foreground/50 font-mono tracking-widest relative">
          <span className="flex flex-col gap-0.5">
            <span>LATENCY</span>
            <strong className={cn("text-xs", latency > 100 ? "text-danger" : latency > 50 ? "text-warning" : "text-success")}>
              {latency > 0 ? `${latency}ms` : '--'}
            </strong>
          </span>

          {/* Interactive Bitrate Selector */}
          <div className="relative pointer-events-auto">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setIsBitrateMenuOpen(!isBitrateMenuOpen)
                setIsResMenuOpen(false)
              }}
              className="flex flex-col gap-0.5 text-left hover:text-primary transition-colors cursor-pointer group/br"
              title="Click to change video bitrate"
            >
              <span className="group-hover/br:text-primary flex items-center gap-0.5">BITRATE ▾</span>
              <strong className="text-white text-xs underline decoration-dotted decoration-primary/60 underline-offset-2">
                {selectedBitrate}
              </strong>
            </button>

            {isBitrateMenuOpen && (
              <div 
                className="absolute bottom-full left-0 mb-2 w-36 bg-black/95 border border-primary/40 rounded-lg shadow-2xl p-1.5 backdrop-blur-md z-30 font-sans pointer-events-auto"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="text-[10px] text-primary/80 font-mono uppercase px-2 py-1 font-semibold border-b border-white/10 mb-1">
                  Bitrate (Speed)
                </div>
                {[
                  { value: '4.2M', label: '4.2 Mbps', desc: 'Ultra Quality' },
                  { value: '2.5M', label: '2.5 Mbps', desc: 'Balanced' },
                  { value: '1.5M', label: '1.5 Mbps', desc: 'Optimized' },
                  { value: '800K', label: '800 Kbps', desc: 'Eco Data Saver' }
                ].map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => handleSelectBitrate(opt.value)}
                    className={cn(
                      "w-full text-left px-2 py-1.5 rounded text-xs flex flex-col transition-all cursor-pointer",
                      selectedBitrate === opt.value
                        ? "bg-primary text-white font-bold"
                        : "text-foreground/80 hover:bg-white/10 hover:text-white"
                    )}
                  >
                    <span>{opt.label}</span>
                    <span className="text-[9px] opacity-70 font-mono">{opt.desc}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Interactive Resolution Selector */}
          <div className="relative pointer-events-auto">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setIsResMenuOpen(!isResMenuOpen)
                setIsBitrateMenuOpen(false)
              }}
              className="flex flex-col gap-0.5 text-left hover:text-primary transition-colors cursor-pointer group/res"
              title="Click to change video resolution"
            >
              <span className="group-hover/res:text-primary flex items-center gap-0.5">RES ▾</span>
              <strong className="text-white text-xs underline decoration-dotted decoration-primary/60 underline-offset-2">
                {selectedRes}
              </strong>
            </button>

            {isResMenuOpen && (
              <div 
                className="absolute bottom-full left-0 mb-2 w-36 bg-black/95 border border-primary/40 rounded-lg shadow-2xl p-1.5 backdrop-blur-md z-30 font-sans pointer-events-auto"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="text-[10px] text-primary/80 font-mono uppercase px-2 py-1 font-semibold border-b border-white/10 mb-1">
                  Resolution
                </div>
                {[
                  { value: '1080p', label: '1080p (FHD)', desc: '1920×1080' },
                  { value: '720p', label: '720p (HD)', desc: '1280×720 Fast' },
                  { value: '480p', label: '480p (SD)', desc: '854×480 Smooth' },
                  { value: '360p', label: '360p (Low)', desc: '640×360 Data' }
                ].map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => handleSelectRes(opt.value)}
                    className={cn(
                      "w-full text-left px-2 py-1.5 rounded text-xs flex flex-col transition-all cursor-pointer",
                      selectedRes === opt.value
                        ? "bg-primary text-white font-bold"
                        : "text-foreground/80 hover:bg-white/10 hover:text-white"
                    )}
                  >
                    <span>{opt.label}</span>
                    <span className="text-[9px] opacity-70 font-mono">{opt.desc}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <span className="text-[10px] text-foreground/30 font-mono uppercase tracking-widest">ID:{id.substring(0,8)}</span>
      </div>

      {/* Floating Controls (Right) */}
      <motion.div 
        initial={{ opacity: 0, x: 20 }}
        whileHover={{ opacity: 1, x: 0 }}
        className="absolute right-2 top-1/2 -translate-y-1/2 flex flex-col gap-2 z-20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-auto"
      >
        {[
          { icon: Maximize, label: 'Fullscreen', action: (e: any) => { e.currentTarget.closest('.group')?.requestFullscreen() } },
          { icon: CameraIcon, label: 'Snapshot', action: () => addToast({ title: 'Hardware Error', message: 'Hardware not supported by this camera model.', type: 'danger' }) },
          { icon: Video, label: 'Record', action: () => addToast({ title: 'Hardware Error', message: 'Hardware not supported by this camera model.', type: 'danger' }) },
          { icon: Crosshair, label: 'PTZ', action: () => addToast({ title: 'Hardware Error', message: 'Hardware not supported by this camera model.', type: 'danger' }) },
          { icon: Mic, label: 'Mic', action: () => addToast({ title: 'Hardware Error', message: 'Hardware not supported by this camera model.', type: 'danger' }) },
          { icon: Volume2, label: 'Audio', action: () => addToast({ title: 'Hardware Error', message: 'Hardware not supported by this camera model.', type: 'danger' }) },
          { icon: PictureInPicture, label: 'PIP', action: () => addToast({ title: 'Picture-in-Picture', message: 'Feature coming soon.', type: 'default' }) },
          { icon: Settings, label: 'Settings', action: () => addToast({ title: 'Hardware Error', message: 'Hardware not supported by this camera model.', type: 'danger' }) },
          { icon: Trash2, label: 'Delete Camera', action: async () => {
              if(confirm('Are you sure you want to delete this camera?')) {
                 try {
                   await api.delete(`/api/cameras/${id}`);
                   addToast({ title: 'Deleted', message: 'Camera deleted successfully.', type: 'success' });
                   window.location.reload();
                 } catch(e) {
                   addToast({ title: 'Error', message: 'Failed to delete camera.', type: 'danger' });
                 }
              }
          }}
        ].map((btn, i) => (
          <motion.button whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }} key={i} onClick={(e) => { e.stopPropagation(); btn.action(e); }} className="p-2 bg-background/60 hover:bg-primary backdrop-blur-sm border border-foreground/10 rounded-lg text-foreground/80 hover:text-white transition-all shadow-lg group/btn relative">
            <btn.icon className="w-4 h-4" />
            <span className="absolute right-full mr-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-background/80 text-[10px] rounded opacity-0 group-hover/btn:opacity-100 pointer-events-none whitespace-nowrap">
              {btn.label}
            </span>
          </motion.button>
        ))}
      </motion.div>

      {isLineEditorOpen && pipelineStatus !== 'Stopped' && (
        <CountingLineEditor
          cameraId={id}
          cameraName={name}
          onClose={() => setIsLineEditorOpen(false)}
        />
      )}

      {isZoneEditorOpen && pipelineStatus !== 'Stopped' && (
        <RestrictedZoneEditor
          cameraId={id}
          cameraName={name}
          onClose={() => setIsZoneEditorOpen(false)}
        />
      )}

      <PluginManagerModal
        cameraId={id}
        isOpen={isPluginModalOpen}
        onClose={() => setIsPluginModalOpen(false)}
      />
    </div>
  )
})

CameraCard.displayName = 'CameraCard'
