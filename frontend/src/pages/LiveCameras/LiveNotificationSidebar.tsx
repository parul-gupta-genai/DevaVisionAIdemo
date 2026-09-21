import { useState, useEffect, useRef } from 'react'
import { Activity, Filter, X, ChevronRight, ChevronLeft } from 'lucide-react'
import { cn } from '@/utils/utils'
import { motion, AnimatePresence } from 'framer-motion'
import { toast } from 'sonner'
import { api } from '@/api/api'
import { useCameraStateStore } from '@/store/useCameraStateStore'

interface LiveEvent {
  id: string
  time: string
  title: string
  cameraName: string
  type: string
  category: string
  snapshot?: string
}

const getCategoryFromTitle = (title: string) => {
  const upper = title?.toUpperCase() || ""
  if (upper.includes("CHECK IN") || upper.includes("CHECK OUT") || upper.includes("ATTENDANCE")) return "ATTENDANCE"
  if (upper.includes("INTRUSION")) return "INTRUSION"
  if (upper.includes("FIRE")) return "SAFETY ALERT"
  if (upper.includes("PERSON COUNT") || upper.includes("PEOPLE")) return "PEOPLE COUNT"
  return "EVENT"
}

const formatEventDateTime = (ts: any): string => {
  if (!ts) return '—';
  const ms = typeof ts === 'number' ? (ts < 1e11 ? ts * 1000 : ts) : new Date(ts).getTime();
  if (!ms || isNaN(ms)) return '—';
  const d = new Date(ms);
  const day = d.getDate();
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'];
  const month = months[d.getMonth()];
  const year = d.getFullYear();
  const time = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  return `${day} ${month} ${year}, ${time}`;
};

export function LiveNotificationSidebar() {
  const [events, setEvents] = useState<LiveEvent[]>([])
  const states = useCameraStateStore(state => state.states)
  const lastKnownId = useRef<string | null>(null)

  // Filters State
  const [showFilters, setShowFilters] = useState(false)
  const [filterCamera, setFilterCamera] = useState("")
  const [filterStartDate, setFilterStartDate] = useState("")
  const [filterEndDate, setFilterEndDate] = useState("")
  const [filterSeverity, setFilterSeverity] = useState("")
  const [filterCategory, setFilterCategory] = useState("")
  const [isCollapsed, setIsCollapsed] = useState(false)
  const [selectedImage, setSelectedImage] = useState<string | null>(null)

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const queryParams = new URLSearchParams()
        if (filterCamera) queryParams.append('camera_id', filterCamera)
        if (filterStartDate) queryParams.append('start_date', new Date(filterStartDate).toISOString())
        if (filterEndDate) queryParams.append('end_date', new Date(filterEndDate).toISOString())
        if (filterSeverity) queryParams.append('severity', filterSeverity)
        if (filterCategory) queryParams.append('category', filterCategory)

        const url = `/events${queryParams.toString() ? '?' + queryParams.toString() : ''}`
        const res = await api.get(url)
        if (res.data && Array.isArray(res.data)) {
          const dbEvents = res.data
          
          const formattedEvents: LiveEvent[] = dbEvents
            .filter((dbEvent: any) => {
              const desc = dbEvent.description?.toLowerCase() || "";
              return !desc.includes('analytics update');
            })
            .map((dbEvent: any, idx: number) => ({
              id: dbEvent.id?.toString() || `${dbEvent.camera_id}-${dbEvent.timestamp}-${idx}`,
              time: formatEventDateTime(dbEvent.timestamp),
              title: dbEvent.description || "No Title",
              cameraName: (dbEvent.camera_name || dbEvent.camera_id || "UNKNOWN").split('/').pop()?.toUpperCase(),
              type: dbEvent.event_type || "info",
              category: getCategoryFromTitle(dbEvent.description),
              snapshot: dbEvent.snapshot_file ? (dbEvent.snapshot_file.startsWith('/') ? dbEvent.snapshot_file : '/' + dbEvent.snapshot_file) : undefined
            }))
          
          if (formattedEvents.length > 0) {
            if (lastKnownId.current !== null) {
              const newIndex = formattedEvents.findIndex(e => e.id === lastKnownId.current);
              if (newIndex > 0) {
                // Trigger toast for new events
                const newEvents = formattedEvents.slice(0, newIndex);
                newEvents.forEach(evt => {
                  const msg = `${evt.category}: ${evt.title}`;
                  if (evt.type === 'danger') toast.error(msg);
                  else if (evt.type === 'warning') toast.warning(msg);
                  else if (evt.type === 'success') toast.success(msg);
                  else toast.info(msg);
                });
              } else if (newIndex === -1 && formattedEvents[0].id !== lastKnownId.current) {
                // If it's completely missing, just toast the latest one
                const evt = formattedEvents[0];
                toast.info(`${evt.category}: ${evt.title}`);
              }
            } else {
              toast.success("Live Notifications Connected", {
                description: "Listening for new AI events..."
              });
            }
            lastKnownId.current = formattedEvents[0].id;
          }
          
          setEvents(formattedEvents);
        }
      } catch (e) {
        console.error("Failed to fetch events", e)
      }
    }

    fetchEvents()
  }, [filterCamera, filterStartDate, filterEndDate, filterSeverity, filterCategory])
  
  // Update on new telemetry events
  useEffect(() => {
    if (states) {
       // Since the websocket doesn't send full historical DB records, 
       // we can either fetch selectively or just refetch when telemetry indicates active events.
       // For now, if there's any active event in telemetry, we re-fetch to get the snapshot from DB.
       // To avoid spamming, we can throttle it, or rely on the fact that telemetry updates 10x/sec.
       // Actually, we'll just keep the initial fetch and add a refresh button for now, or fetch when new events appear.
    }
  }, [states])

  return (
    <div className="relative h-full flex shrink-0">
      <button 
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="absolute top-1/2 -left-6 -translate-y-1/2 bg-[#030014]/90 border-y border-l border-foreground/10 text-muted-foreground hover:text-white p-1 rounded-l-md hover:bg-foreground/10 z-20 backdrop-blur-xl transition-colors shadow-[-5px_0_15px_rgba(0,0,0,0.5)]"
      >
        {isCollapsed ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>

      <motion.aside 
        initial={false}
        animate={{ 
          width: isCollapsed ? 0 : 320,
          opacity: isCollapsed ? 0 : 1
        }}
        className="bg-[#030014]/80 backdrop-blur-3xl border-l border-foreground/5 flex flex-col h-full shadow-[0_0_50px_rgba(124,58,237,0.15)] relative z-10 overflow-hidden shrink-0"
      >
        <div className="w-80 h-full flex flex-col shrink-0">
          <div className="p-4 border-b border-foreground/5 flex flex-col shrink-0 bg-background/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-danger animate-pulse shadow-[0_0_8px_rgba(244,63,94,0.8)]" />
            <h2 className="text-sm font-bold tracking-widest text-primary uppercase">Global Event Stream</h2>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-white font-bold bg-foreground/10 px-3 py-1 rounded-full uppercase tracking-wider shadow-inner shadow-white/5">
              {events.length} Captured
            </span>
            <button 
              onClick={() => setShowFilters(!showFilters)}
              className={cn(
                "p-1.5 rounded-md transition-colors hover:bg-foreground/10",
                showFilters ? "bg-primary/20 text-primary" : "text-muted-foreground"
              )}
            >
              <Filter className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filters Panel */}
        <AnimatePresence>
          {showFilters && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="pt-4 flex flex-col gap-3">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Filters</span>
                  <button 
                    onClick={() => {
                      setFilterCamera("")
                      setFilterStartDate("")
                      setFilterEndDate("")
                      setFilterSeverity("")
                      setFilterCategory("")
                    }}
                    className="text-[10px] text-primary hover:underline"
                  >
                    Clear All
                  </button>
                </div>
                
                <input 
                  type="text" 
                  placeholder="Camera ID..." 
                  value={filterCamera}
                  onChange={(e) => setFilterCamera(e.target.value)}
                  className="w-full bg-background/40 border border-foreground/10 rounded-md px-2 py-1.5 text-xs text-white placeholder:text-muted-foreground focus:outline-none focus:border-primary/50"
                />

                <div className="flex gap-2">
                  <div className="flex-1">
                    <label className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1 block">Start Time</label>
                    <input 
                      type="datetime-local" 
                      value={filterStartDate}
                      onChange={(e) => setFilterStartDate(e.target.value)}
                      className="w-full bg-background/40 border border-foreground/10 rounded-md px-2 py-1.5 text-xs text-white focus:outline-none focus:border-primary/50 [color-scheme:dark]"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1 block">End Time</label>
                    <input 
                      type="datetime-local" 
                      value={filterEndDate}
                      onChange={(e) => setFilterEndDate(e.target.value)}
                      className="w-full bg-background/40 border border-foreground/10 rounded-md px-2 py-1.5 text-xs text-white focus:outline-none focus:border-primary/50 [color-scheme:dark]"
                    />
                  </div>
                </div>

                <div className="flex gap-2">
                  <select 
                    value={filterSeverity}
                    onChange={(e) => setFilterSeverity(e.target.value)}
                    className="flex-1 bg-background/40 border border-foreground/10 rounded-md px-2 py-1.5 text-xs text-white focus:outline-none focus:border-primary/50"
                  >
                    <option value="">Any Severity</option>
                    <option value="info">Info</option>
                    <option value="warning">Warning</option>
                    <option value="danger">Danger</option>
                    <option value="success">Success</option>
                  </select>

                  <select 
                    value={filterCategory}
                    onChange={(e) => setFilterCategory(e.target.value)}
                    className="flex-1 bg-background/40 border border-foreground/10 rounded-md px-2 py-1.5 text-xs text-white focus:outline-none focus:border-primary/50"
                  >
                    <option value="">Any Category</option>
                    <option value="ATTENDANCE">Attendance</option>
                    <option value="INTRUSION">Intrusion</option>
                    <option value="SAFETY ALERT">Safety Alert</option>
                    <option value="PEOPLE COUNT">People Count</option>
                  </select>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-muted-foreground gap-2">
            <Activity className="w-8 h-8 opacity-20" />
            <span className="text-sm font-medium opacity-50">Awaiting Events...</span>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {events.map((event, i) => (
              <motion.div 
                key={event.id}
                initial={{ opacity: 0, y: -20, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ type: "spring", stiffness: 300, damping: 20 }}
                className="min-h-[80px] shrink-0 flex rounded-xl overflow-hidden bg-background/40 border border-foreground/5 shadow-lg backdrop-blur-sm transition-all hover:bg-background/60 hover:border-foreground/10 group"
              >
              <div className={cn(
                "w-1 shrink-0",
                event.type === 'danger' && "bg-danger shadow-[0_0_10px_rgba(244,63,94,0.5)]",
                event.type === 'warning' && "bg-warning shadow-[0_0_10px_rgba(245,158,11,0.5)]",
                event.type === 'success' && "bg-success shadow-[0_0_10px_rgba(16,185,129,0.5)]",
                event.type === 'info' && "bg-primary shadow-[0_0_10px_rgba(124,58,237,0.5)]"
              )} />
              
              <div className="p-3 w-full flex items-center gap-3">
                {event.snapshot && (
                  <div 
                    className="w-16 h-16 shrink-0 rounded-md overflow-hidden border border-foreground/10 bg-black/40 flex items-center justify-center cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => setSelectedImage(event.snapshot!)}
                  >
                    <img 
                      src={event.snapshot} 
                      alt="Event snapshot" 
                      className="w-full h-full object-contain"
                    />
                  </div>
                )}
                
                <div className="flex-1 flex flex-col justify-center overflow-hidden">
                  <div className="flex justify-between items-center mb-1">
                  <div className="flex items-center gap-2">
                    <div className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      event.type === 'danger' && "bg-danger",
                      event.type === 'warning' && "bg-warning",
                      event.type === 'success' && "bg-success",
                      event.type === 'info' && "bg-primary"
                    )} />
                    <span className="text-[10px] font-bold tracking-wider text-white">
                      {event.cameraName}
                    </span>
                  </div>
                  <span className="text-[10px] text-gray-400 font-mono tracking-wider">
                    {event.time}
                  </span>
                </div>
                
                <div className={cn(
                  "text-[10px] font-bold tracking-widest uppercase mb-1",
                  event.type === 'danger' && "text-danger",
                  event.type === 'warning' && "text-warning",
                  event.type === 'success' && "text-success",
                  event.type === 'info' && "text-primary"
                )}>
                  {event.category}
                </div>
                
                <div className="text-sm text-gray-300 font-medium leading-snug break-words">
                  {event.title}
                </div>

                </div>
              </div>
            </motion.div>
          ))}
          </AnimatePresence>
        )}
      </div>
      </div>
    </motion.aside>

    <AnimatePresence>
      {selectedImage && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setSelectedImage(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
        >
          <motion.img
            initial={{ scale: 0.9 }}
            animate={{ scale: 1 }}
            exit={{ scale: 0.9 }}
            src={selectedImage}
            alt="Enlarged snapshot"
            className="max-w-full max-h-full rounded-xl shadow-2xl border border-white/20"
            onClick={(e) => e.stopPropagation()}
          />
          <button 
            onClick={() => setSelectedImage(null)}
            className="absolute top-4 right-4 text-white/70 hover:text-white bg-black/50 hover:bg-black/80 p-2 rounded-full transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  </div>
)
}
