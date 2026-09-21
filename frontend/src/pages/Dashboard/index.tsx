import { WeatherWidget } from '@/components/dashboard/WeatherWidget'
import { ConstructionProgressWidget } from '@/components/dashboard/ConstructionProgressWidget'
import { DailySiteReportModal } from '@/components/dashboard/DailySiteReportModal'
import { useCameraStateStore } from '@/store/useCameraStateStore'
import { api } from '@/api/api'
import { Video, AlertTriangle, Cpu, HardDrive, Network, ShieldCheck, Activity, Users, HardHat, Car, Box, CheckCircle, Thermometer, Clock, Server, Database, PlayCircle, FileText } from 'lucide-react'
import { MiniChart } from '@/components/analytics/MiniChart'
import { motion, AnimatePresence } from 'framer-motion'
import { useEffect, useState, useRef, useCallback } from 'react'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { staggerContainer, fadeInUp, scaleUp } from '@/utils/animations'
import { AIBrain } from '@/components/ui/AIBrain'

function ActiveAlertsPanel({ events }: { events: any[] }) {
  const handleAction = (action: string, id: string) => {
    alert(`${action} triggered for event ${id}`);
  };

  return (
    <div className="glass-panel rounded-3xl p-5 border-border flex flex-col relative w-full h-[650px] z-10 overflow-hidden">
      <h3 className="text-sm font-bold tracking-widest uppercase mb-4 text-danger drop-shadow-md flex items-center gap-2 shrink-0">
        <AlertTriangle className="animate-pulse w-4 h-4" /> Active Critical Alerts
      </h3>
      <div className="flex flex-col gap-3 overflow-y-auto custom-scrollbar flex-1 pr-1 -mr-1">
        {events.length === 0 ? (
           <div className="text-muted-foreground p-4 text-center glass rounded-xl border border-foreground/5 text-sm">No active critical alerts.</div>
        ) : events.map(evt => (
          <div key={evt.id} className={`p-3 rounded-xl border flex flex-col gap-3 shrink-0 ${evt.event_type === 'danger' ? 'bg-danger/10 border-danger/30' : 'bg-warning/10 border-warning/30'}`}>
            <div className="flex items-start gap-3">
              <div className={`p-2 rounded-full shrink-0 ${evt.event_type === 'danger' ? 'bg-danger/20 text-danger' : 'bg-warning/20 text-warning'}`}>
                {evt.event_type === 'danger' ? <AlertTriangle className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="font-bold text-foreground text-sm leading-tight truncate" title={evt.description}>{evt.description}</h4>
                <p className="text-xs text-muted-foreground mt-1 truncate">{new Date(evt.timestamp).toLocaleTimeString()} — {evt.camera_name}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button onClick={() => handleAction('View Live', evt.id)} className="px-2 py-1.5 text-[10px] font-bold bg-primary/20 hover:bg-primary/40 text-primary rounded transition-colors truncate">View Live</button>
              {evt.snapshot_file ? (
                <a href={evt.snapshot_file} target="_blank" rel="noreferrer" className="px-2 py-1.5 text-[10px] text-center font-bold bg-foreground/10 hover:bg-foreground/20 text-foreground rounded transition-colors truncate">Snapshot</a>
              ) : (
                <button onClick={() => handleAction('Video', evt.id)} className="px-2 py-1.5 text-[10px] font-bold bg-foreground/10 hover:bg-foreground/20 text-foreground rounded transition-colors truncate">Video</button>
              )}
              <button onClick={() => handleAction('Acknowledge', evt.id)} className="px-2 py-1.5 text-[10px] font-bold bg-accent/20 hover:bg-accent/40 text-accent rounded transition-colors truncate">Acknowledge</button>
              <button onClick={() => handleAction('Resolve', evt.id)} className="px-2 py-1.5 text-[10px] font-bold bg-success/20 hover:bg-success/40 text-success rounded transition-colors flex items-center justify-center gap-1 truncate">
                <CheckCircle className="w-3 h-3 shrink-0" /> Resolve
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function StatCard({ title, value, icon: Icon, trend, color, data, isCameras, online, offline, isPeople, workers, staff, visitors }: any) {
  return (
    <motion.div 
      variants={fadeInUp}
      whileHover={{ y: -5, scale: 1.02 }}
      className="glass-pro p-5 rounded-2xl flex flex-col gap-4 relative overflow-hidden group cursor-pointer transition-all duration-300 min-h-[140px]"
    >
      <div className="flex justify-between items-start z-10">
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground font-medium text-xs tracking-widest uppercase">{title}</span>
          <span className="text-3xl font-bold tracking-tight text-foreground dark:text-white drop-shadow-sm">{value}</span>
        </div>
        <div className={`p-2.5 rounded-xl bg-foreground/5 border border-foreground/10 shadow-sm group-hover:scale-110 group-hover:bg-foreground/10 transition-all`}>
          <Icon className="w-5 h-5 drop-shadow-md" style={{ color }} />
        </div>
      </div>
      
      <div className="flex justify-between items-end z-10 mt-auto">
        {isCameras ? (
          <div className="flex gap-3 text-xs font-medium">
            <span className="text-success flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-success"></div> {online} Online</span>
            <span className="text-danger flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-danger"></div> {offline} Offline</span>
          </div>
        ) : isPeople ? (
          <div className="flex gap-3 text-xs font-medium text-muted-foreground">
            <span>Workers: <strong className="text-foreground">{workers}</strong></span>
            <span>Staff: <strong className="text-foreground">{staff}</strong></span>
            <span>Visitors: <strong className="text-foreground">{visitors}</strong></span>
          </div>
        ) : (
          <>
            {trend !== undefined && (
              <span className={`text-[10px] font-bold px-2 py-1 rounded-md ${trend > 0 ? 'bg-success/20 text-success border border-success/30' : trend < 0 ? 'bg-danger/20 text-danger border border-danger/30' : 'bg-foreground/10 text-muted-foreground border border-foreground/10'}`}>
                {trend > 0 ? '+' : ''}{trend}%
              </span>
            )}
            {data && (
              <div className="w-24 h-8 opacity-70 group-hover:opacity-100 transition-opacity">
                <MiniChart data={data.map((d: any) => ({...d}))} color={color} />
              </div>
            )}
          </>
        )}
      </div>

      <div 
        className="absolute -bottom-10 -right-10 w-32 h-32 blur-[50px] opacity-20 group-hover:opacity-40 transition-opacity rounded-full pointer-events-none"
        style={{ backgroundColor: color }}
      />
    </motion.div>
  )
}

export function Dashboard() {
  const [mounted, setMounted] = useState(false)
  const [sysData, setSysData] = useState<any>(null)
  const [criticalEvents, setCriticalEvents] = useState<any[]>([])
  const [reportModalOpen, setReportModalOpen] = useState(false)

  const cpuHistory = useRef<{value: number}[]>([])
  const ramHistory = useRef<{value: number}[]>([])
  const alertHistory = useRef<{value: number}[]>([])
  const telemetryHistory = useRef<{time: string, load: number, ram: number}[]>([])

  const pushHistory = useCallback((arrRef: any, val: number) => {
    const newArr = [...arrRef.current, { value: val }]
    if (newArr.length > 15) newArr.shift()
    arrRef.current = newArr
  }, [])

  const states = useCameraStateStore(state => state.states);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await api.get('/events')
      if (res.data && Array.isArray(res.data)) {
        const filtered = res.data.filter((e: any) => e.event_type === 'danger' || e.event_type === 'warning').slice(0, 5)
        setCriticalEvents(filtered)
      }
    } catch (err) {}
  }, [])

  useEffect(() => {
    setMounted(true)
    const fetchInitial = async () => {
      try {
        const res = await api.get('/analytics/dashboard')
        if (res.data) setSysData((prev: any) => ({ ...prev, ...res.data }))
      } catch (err) {}
    }
    fetchInitial()
    fetchEvents()
    const interval = setInterval(() => {
      fetchInitial();
      fetchEvents();
    }, 10000)
    return () => clearInterval(interval)
  }, [fetchEvents])

  useEffect(() => {
    if (states && sysData?.system_health) {
      const h = sysData.system_health;
      const newCpu = h.cpu_usage ?? 0;
      const newRam = h.ram_usage ?? 0;
      pushHistory(cpuHistory, newCpu)
      pushHistory(ramHistory, newRam)

      const now = new Date()
      const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
      telemetryHistory.current.push({ time: timeStr, load: newCpu, ram: newRam })
      if (telemetryHistory.current.length > 30) telemetryHistory.current.shift()
    }
  }, [states, sysData?.system_health, pushHistory]);

  const hasCameras = (sysData?.total_cameras ?? 0) > 0;

  const stats = [
    { 
      title: "Site Overview", 
      isCameras: true, 
      value: `${sysData?.total_cameras ?? 0} Cameras`, 
      online: sysData?.online_cameras ?? 0, 
      offline: sysData?.offline_cameras ?? 0,
      icon: Video, color: "var(--color-primary)" 
    },
    { 
      title: "People On Site", 
      isPeople: true,
      value: hasCameras ? (sysData?.people_on_site?.total ?? 0) : 0, 
      workers: hasCameras ? (sysData?.people_on_site?.workers ?? 0) : 0,
      staff: hasCameras ? (sysData?.people_on_site?.staff ?? 0) : 0,
      visitors: hasCameras ? (sysData?.people_on_site?.visitors ?? 0) : 0,
      icon: Users, color: "var(--color-info)" 
    },
    { title: "Critical Alerts", value: hasCameras ? (sysData?.critical_alerts ?? 0) : 0, icon: AlertTriangle, color: "var(--color-danger)" },
    { title: "Safety Score", value: hasCameras ? `${sysData?.safety_score ?? 0}%` : "—", icon: ShieldCheck, color: "var(--color-success)" },
    { title: "PPE Compliance", value: hasCameras ? `${sysData?.ppe_compliance ?? 0}%` : "—", icon: HardHat, color: "var(--color-warning)" },
    { title: "Vehicles Inside", value: hasCameras ? (sysData?.vehicles_inside ?? 0) : 0, icon: Car, color: "var(--color-accent)" },
    { title: "Material Events", value: hasCameras ? (sysData?.material_events ?? 0) : 0, icon: Box, color: "var(--color-primary)" },
  ]

  if (!mounted) return null

  return (
    <div className="p-8 pb-24 h-full overflow-y-auto custom-scrollbar relative">
      <div className="absolute top-0 left-0 w-full h-96 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />

      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-between items-end mb-10 relative z-10"
      >
        <div>
          <h1 className="text-4xl font-extrabold tracking-tight mb-2 text-gradient">Command Center</h1>
          <p className="text-muted-foreground font-medium tracking-wide">Real-time enterprise telemetry and AI analytics.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setReportModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-full glass border border-primary/30 hover:border-primary text-primary hover:bg-primary/10 text-xs font-bold transition-all shadow-sm"
          >
            <FileText className="w-4 h-4" /> Daily Site Report
          </button>
          <div className="hidden md:flex items-center gap-3 glass px-4 py-2 rounded-full border border-foreground/10">
            <div className="w-2 h-2 rounded-full bg-success animate-pulse glow-success" />
            <span className="text-xs font-bold text-success tracking-widest uppercase">Live Data Stream</span>
          </div>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-8 relative z-10">
        {/* Left Side: Stats and Charts */}
        <div className="xl:col-span-3 flex flex-col gap-8">
          <motion.div 
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6"
          >
            {stats.map((stat) => (
              <StatCard key={stat.title} {...stat} />
            ))}
          </motion.div>

          {/* Construction Specific Widgets Row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <WeatherWidget />
            <ConstructionProgressWidget />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <motion.div 
              variants={scaleUp}
              initial="hidden"
              animate="visible"
              className="lg:col-span-1 glass-pro rounded-3xl p-1 h-[450px] border border-foreground/10 flex flex-col relative overflow-hidden group"
            >
              <div className="absolute top-6 left-6 z-10">
                 <h3 className="text-sm font-bold tracking-widest uppercase text-foreground drop-shadow-md">DevaVision AI</h3>
                 <p className="text-xs text-primary glow-primary mt-1">Edge Neural Engine</p>
              </div>

              <div className="flex-1 w-full rounded-2xl overflow-hidden bg-background/20">
                <AIBrain />
              </div>
            </motion.div>

            <motion.div 
              variants={fadeInUp}
              initial="hidden"
              animate="visible"
              className="lg:col-span-2 glass-panel rounded-3xl p-6 h-[450px] border-border flex flex-col relative"
            >
              <h3 className="text-sm font-bold tracking-widest uppercase mb-6 text-foreground drop-shadow-md">System Telemetry (Live)</h3>
              <div className="flex-1 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={telemetryHistory.current.length > 0 ? telemetryHistory.current.map(obj => ({...obj})) : [{ time: '—', load: 0, ram: 0 }]}>
                    <defs>
                      <linearGradient id="colorLoad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--color-primary)" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="var(--color-primary)" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorEvents" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--color-accent)" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="var(--color-accent)" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                    <XAxis dataKey="time" stroke="#666" tick={{fill: '#666', fontSize: 12}} tickLine={false} axisLine={false} />
                    <YAxis stroke="#666" tick={{fill: '#666', fontSize: 12}} tickLine={false} axisLine={false} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: 'rgba(10,10,10,0.8)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px', backdropFilter: 'blur(10px)', color: '#fff' }} 
                      itemStyle={{ color: '#fff' }}
                    />
                    <Area type="monotone" dataKey="load" stroke="var(--color-primary)" strokeWidth={3} fillOpacity={1} fill="url(#colorLoad)" name="CPU Load %" />
                    <Area type="monotone" dataKey="ram" stroke="var(--color-accent)" strokeWidth={3} fillOpacity={1} fill="url(#colorEvents)" name="RAM Usage %" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </motion.div>
          </div>
        </div>

        {/* Right Side: Active Alerts */}
        <div className="xl:col-span-1 h-full">
          <ActiveAlertsPanel events={criticalEvents} />
        </div>
      </div>

      {/* Daily Site Safety & Operations Report Modal */}
      <DailySiteReportModal isOpen={reportModalOpen} onClose={() => setReportModalOpen(false)} />
    </div>
  )
}
