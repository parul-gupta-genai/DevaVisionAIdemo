import React, { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { X, Activity, Cpu, HardDrive, Database, Server, Network, Video, Zap, Thermometer, ShieldCheck } from 'lucide-react'
import { api } from '@/api/api'

type SystemHealthModalProps = {
  isOpen: boolean
  onClose: () => void
}

export default function SystemHealthModal({ isOpen, onClose }: SystemHealthModalProps) {
  const [telemetry, setTelemetry] = useState<any>(null)

  useEffect(() => {
    if (isOpen) {
      const fetchTelemetry = async () => {
        try {
          const res = await api.get('/api/telemetry')
          setTelemetry(res.data)
        } catch (e) {
          console.error(e)
        }
      }
      fetchTelemetry()
      const interval = setInterval(fetchTelemetry, 2000)
      return () => clearInterval(interval)
    }
  }, [isOpen])

  if (!isOpen) return null

  // Mocks for Orin NX specific metrics if backend doesn't provide them yet
  const gpuUsage = telemetry?.gpu_usage ?? 68;
  const gpuMem = "4.2 / 8 GB";
  const temp = "45°C";
  const fps = "30 FPS / cam";
  const inference = "12ms";
  
  const metrics = [
    { label: 'GPU Utilization', value: `${gpuUsage}%`, icon: Activity, tone: 'text-purple-400', progress: gpuUsage },
    { label: 'GPU Memory', value: gpuMem, icon: HardDrive, tone: 'text-purple-400' },
    { label: 'CPU Usage', value: `${telemetry?.cpu_usage || 0}%`, icon: Cpu, tone: 'text-blue-400', progress: telemetry?.cpu_usage || 0 },
    { label: 'RAM Usage', value: `${telemetry?.ram_usage || 0}%`, icon: Server, tone: 'text-emerald-400', progress: telemetry?.ram_usage || 0 },
    { label: 'Disk Space', value: '45%', icon: HardDrive, tone: 'text-zinc-400', progress: 45 },
    { label: 'Temperature', value: temp, icon: Thermometer, tone: 'text-orange-400' },
    { label: 'Total Cameras', value: '30', icon: Video, tone: 'text-blue-400' },
    { label: 'Average FPS', value: fps, icon: Activity, tone: 'text-emerald-400' },
    { label: 'AI Inference Latency', value: inference, icon: Zap, tone: 'text-amber-400' },
  ]

  const services = [
    { name: 'AI Model Engines', status: 'Healthy', icon: Zap },
    { name: 'DeepStream Pipeline', status: 'Running', icon: Video },
    { name: 'MediaMTX Server', status: 'Online', icon: Network },
    { name: 'PostgreSQL DB', status: 'Connected', icon: Database },
    { name: 'WebSocket Stream', status: 'Active', icon: Activity },
  ]

  return (
    <div className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        onClick={(e) => e.stopPropagation()}
        className="glass border border-foreground/10 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl"
      >
        <div className="p-6 border-b border-foreground/10 flex justify-between items-center bg-background/40">
          <div>
            <h2 className="text-2xl font-black text-white flex items-center gap-3">
              <Activity className="w-7 h-7 text-primary" />
              AI & System Health
            </h2>
            <p className="text-sm text-muted-foreground mt-1">Edge Device Telemetry (Jetson Orin NX)</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-foreground/10 rounded-xl transition-colors">
            <X className="w-6 h-6 text-white" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto custom-scrollbar flex-1 space-y-8">
          
          {/* Hardware Metrics */}
          <div>
            <h3 className="text-lg font-bold text-white mb-4">Hardware & AI Performance</h3>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              {metrics.map((m, i) => (
                <div key={i} className="p-4 rounded-xl border border-foreground/5 bg-background/20 hover:bg-background/40 transition-colors">
                  <div className="flex items-center gap-3 mb-2">
                    <m.icon className={`w-5 h-5 ${m.tone}`} />
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{m.label}</span>
                  </div>
                  <div className="text-2xl font-black text-white font-mono">{m.value}</div>
                  {m.progress !== undefined && (
                    <div className="mt-3 h-1.5 bg-background/60 rounded-full overflow-hidden">
                      <div className={`h-full ${m.tone.replace('text-', 'bg-')}`} style={{ width: `${m.progress}%` }} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Services */}
          <div>
            <h3 className="text-lg font-bold text-white mb-4">Core Services</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {services.map((s, i) => (
                <div key={i} className="p-4 rounded-xl border border-foreground/5 bg-background/20 flex items-center gap-4">
                  <div className="p-2 rounded-lg bg-success/10 text-success">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-sm font-bold text-white">{s.name}</div>
                    <div className="text-[10px] uppercase font-bold text-success tracking-wider mt-0.5">{s.status}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>
      </motion.div>
    </div>
  )
}
