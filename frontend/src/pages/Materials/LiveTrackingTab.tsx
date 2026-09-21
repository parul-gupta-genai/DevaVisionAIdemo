import React, { useEffect, useState } from 'react';
import { Package, Activity } from 'lucide-react';
import { api } from '@/api/api';
import { useCameraStateStore } from '@/store/useCameraStateStore';

export default function LiveTrackingTab() {
  const [liveCounts, setLiveCounts] = useState<any>({});
  const states = useCameraStateStore(state => state.states);

  useEffect(() => {
    if (states) {
      setLiveCounts((prev: any) => {
        const nc = { ...prev };
        Object.values(states).forEach((s: any) => {
          const evts = s.events?.CartonAnalyticsPlugin || [];
          evts.forEach((e: any) => {
             if (e.event_type === 'CARTON_COUNT') {
                nc[s.camera_id] = e.metadata?.count || 0;
             }
          });
        });
        return nc;
      });
    }
  }, [states]);

  const cams = Object.keys(liveCounts);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide">Live Material Tracking</h2>
          <p className="text-sm text-muted-foreground">Real-time object detection streams across cameras.</p>
        </div>
      </div>

      {cams.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground glass rounded-2xl">
          No live material tracking data available. Ensure cameras are active.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {cams.map((camId) => (
             <div key={camId} className="glass border border-foreground/10 rounded-2xl p-6 relative overflow-hidden group">
               <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-[40px] group-hover:bg-primary/20 transition-colors pointer-events-none -mr-10 -mt-10" />
               <div className="flex justify-between items-start mb-6 relative z-10">
                 <div>
                   <div className="text-[10px] uppercase font-bold tracking-widest text-primary mb-1">Camera Stream</div>
                   <div className="font-bold text-white truncate max-w-[200px]" title={camId}>{camId}</div>
                 </div>
                 <div className="p-3 bg-background/50 rounded-xl border border-foreground/5 shadow-inner">
                   <Activity className="w-5 h-5 text-primary animate-pulse" />
                 </div>
               </div>
               
               <div className="flex items-center gap-4 relative z-10">
                 <div className="flex-1">
                   <div className="text-sm text-muted-foreground mb-1">Detected Cartons</div>
                   <div className="text-4xl font-black text-white">{liveCounts[camId] || 0}</div>
                 </div>
                 <Package className="w-16 h-16 text-foreground/5" />
               </div>
             </div>
          ))}
        </div>
      )}
    </div>
  );
}
