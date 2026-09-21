import { useEffect, useState } from 'react'
import { Car, Clock, ShieldCheck, AlertCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/utils'
import { api } from '@/api/api'
import { useCameraStateStore } from '@/store/useCameraStateStore'

export default function ParkingTab() {
  const [stats, setStats] = useState<any>({})
  const [loading, setLoading] = useState(true)
  const states = useCameraStateStore(state => state.states)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await api.get('/api/parking/stats')
        if (res.data?.current) {
          setStats(res.data.current)
        }
      } catch (err) {
        console.error("Failed to fetch parking data", err)
      } finally {
        setLoading(false)
      }
    }
    
    fetchData()
  }, [])
  
  // Overlay live websocket data
  useEffect(() => {
    if (states) {
      setStats((prevStats: any) => {
         const newStats = { ...prevStats };
         Object.values(states || {}).forEach((state: any) => {
            const evts = state.events?.ParkingAnalyticsPlugin || [];
            evts.forEach((e: any) => {
               if (e.event_type === 'PARKING_STATS') {
                  newStats[state.camera_id] = {
                      ...newStats[state.camera_id],
                      occupied_spots: e.metadata?.occupied_spots || 0,
                      available_spots: e.metadata?.available_spots || 0,
                      total_spots: e.metadata?.total_spots || 0,
                      spot_status: e.metadata?.spot_status || []
                  };
               }
            });
         });
         return newStats;
      });
    }
  }, [states]);

  if (loading) {
    return <div className="p-8 flex items-center justify-center h-full"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" /></div>
  }

  const cameraKeys = Object.keys(stats)

  return (
    <div className="p-8 h-full overflow-y-auto">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-4xl font-extrabold tracking-tight mb-2 text-gradient">Parking Analytics</h1>
          <p className="text-muted-foreground font-medium tracking-wide">Live occupancy tracking across defined parking zones.</p>
        </div>
      </div>

      {cameraKeys.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground glass rounded-2xl">
          No parking stats found. Please ensure Parking zones are configured in the backend and vehicles are detected.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {cameraKeys.map((camId, i) => {
            const data = stats[camId]
            const utilization = data.total_spots > 0 ? (data.occupied_spots / data.total_spots) * 100 : 0
            
            return (
              <motion.div 
                key={camId}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ type: 'spring', stiffness: 300, damping: 20, delay: i * 0.1 }}
                whileHover={{ y: -5, scale: 1.01 }}
                className="glass-pro rounded-3xl border border-foreground/5 overflow-hidden flex flex-col group cursor-pointer transition-all duration-300"
              >
                {/* Header Graphic */}
                <div className="h-28 bg-background/40 relative flex items-center justify-between px-8 border-b border-foreground/5">
                  <div className="absolute top-0 right-0 w-48 h-48 bg-primary/20 rounded-full blur-[50px] group-hover:opacity-100 opacity-50 transition-opacity pointer-events-none -mr-16 -mt-16" />
                  <div className="flex flex-col relative z-10">
                    <span className="text-[10px] font-bold text-primary uppercase tracking-widest mb-1">Camera Stream</span>
                    <span className="text-xl font-black text-white truncate max-w-[150px] drop-shadow-md" title={camId}>
                      {camId.split('/').pop() || camId}
                    </span>
                  </div>
                  <div className="relative z-10 w-14 h-14 rounded-2xl bg-foreground/5 border border-foreground/10 flex items-center justify-center shadow-lg backdrop-blur-md group-hover:scale-110 transition-transform">
                    <Car className={cn("w-6 h-6", utilization > 90 ? "text-danger" : "text-primary")} />
                  </div>
                </div>
                
                {/* Stats */}
                <div className="p-6 flex flex-col gap-6">
                  <div className="flex justify-between items-end">
                    <div>
                      <div className="text-3xl font-bold tracking-tight text-white mb-1">
                        {data.available_spots}
                      </div>
                      <div className="flex items-center gap-2 text-sm text-success font-medium">
                        <ShieldCheck className="w-4 h-4" /> Available Slots
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-3xl font-bold tracking-tight text-white mb-1">
                        {data.occupied_spots}
                      </div>
                      <div className="flex items-center justify-end gap-2 text-sm text-danger font-medium">
                        <AlertCircle className="w-4 h-4" /> Occupied
                      </div>
                    </div>
                  </div>
                  
                  {/* Utilization Bar */}
                  <div>
                    <div className="flex justify-between text-xs text-muted-foreground mb-2">
                      <span>Utilization</span>
                      <span>{Math.round(utilization)}%</span>
                    </div>
                    <div className="w-full h-2 bg-background/40 rounded-full overflow-hidden">
                      <div 
                        className={cn("h-full transition-all duration-1000 ease-out", 
                          utilization > 90 ? "bg-danger" : utilization > 60 ? "bg-warning" : "bg-primary"
                        )}
                        style={{ width: `${utilization}%` }}
                      />
                    </div>
                  </div>
                  
                  {/* Spot Map Mock */}
                  <div className="mt-4 border-t border-foreground/5 pt-4">
                    <div className="text-xs font-medium text-muted-foreground mb-3 uppercase tracking-wider">Live Slot Map</div>
                    <div className="flex gap-2 flex-wrap">
                      {data.spot_status.map((isOccupied: boolean, idx: number) => (
                        <div 
                          key={idx}
                          className={cn(
                            "px-3 py-1.5 rounded text-xs font-bold transition-colors",
                            isOccupied ? "bg-danger/20 text-danger border border-danger/30" : "bg-success/20 text-success border border-success/30"
                          )}
                        >
                          P{idx + 1}
                        </div>
                      ))}
                    </div>
                  </div>
                  
                </div>
              </motion.div>
            )
          })}
        </div>
      )}
    </div>
  )
}
