import React, { useMemo } from 'react';
import { ShieldAlert, CheckCircle2, AlertTriangle, UserCheck, HardHat, ShieldCheck, ChevronRight, Users } from 'lucide-react';
import { useCameraStateStore } from '@/store/useCameraStateStore';
import { motion } from 'framer-motion';
import { cn } from '@/utils/utils';

export default function ContractorsTab() {
  const { states } = useCameraStateStore();

  const realTimeStats = useMemo(() => {
    let blueCount = 0;
    let yellowCount = 0;
    Object.values(states).forEach((state: any) => {
      const ppeEvents = state.events?.PPEDetectionPlugin || [];
      const statsEvent = ppeEvents.find((e: any) => e.event_type === "PPE_STATS");
      if (statsEvent?.metadata) {
        blueCount += statsEvent.metadata.contractor_1_count || 0;
        yellowCount += statsEvent.metadata.contractor_2_count || 0;
      }
    });
    return { blueCount, yellowCount };
  }, [states]);

  const MetricItem = ({ label, value, icon: Icon, colorClass, highlight = false }: any) => (
    <div className={cn("flex items-center justify-between p-3 rounded-lg border", highlight ? `bg-${colorClass}/10 border-${colorClass}/20` : "bg-background/40 border-foreground/5")}>
      <div className="flex items-center gap-2">
        <Icon className={cn("w-4 h-4", `text-${colorClass}`)} />
        <span className="text-xs text-muted-foreground uppercase font-bold tracking-wider">{label}</span>
      </div>
      <span className={cn("font-black text-sm", highlight ? `text-${colorClass}` : "text-white")}>{value}</span>
    </div>
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
      {/* Contractor Alpha */}
      <motion.div 
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        className="glass-panel p-6 border-t-4 border-t-blue-500 relative overflow-hidden flex flex-col"
      >
        <div className="absolute top-0 right-0 p-6 opacity-5 pointer-events-none">
          <ShieldAlert className="w-48 h-48 text-blue-500" />
        </div>
        
        <div className="flex justify-between items-start mb-6 relative z-10">
          <div>
            <h2 className="text-2xl font-black text-white tracking-wide flex items-center gap-2">
              Contractor Alpha
              <span className="px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30 text-[9px] uppercase tracking-widest">Blue PPE</span>
            </h2>
            <div className="text-sm text-gray-400 mt-1 font-medium">Electrical & HVAC</div>
          </div>
          <div className="text-right">
            <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold">Safety Score</span>
            <div className="text-3xl font-black text-success mt-1">92</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-6 relative z-10">
          <MetricItem label="Workers" value="42" icon={Users} colorClass="blue-400" />
          <MetricItem label="Present (Live)" value={realTimeStats.blueCount || 38} icon={UserCheck} colorClass="success" />
          <MetricItem label="PPE Compliance" value="96%" icon={HardHat} colorClass="blue-400" />
          <MetricItem label="PPE Violations" value="3" icon={AlertTriangle} colorClass="warning" highlight={true} />
          <MetricItem label="Zone Breaches" value="1" icon={ShieldCheck} colorClass="danger" highlight={true} />
          <div className="flex items-center justify-between p-3 rounded-lg border bg-background/40 border-foreground/5">
            <span className="text-xs text-muted-foreground uppercase font-bold tracking-wider">Supervisor</span>
            <span className="font-bold text-sm text-white truncate max-w-[100px]" title="Surender Singh">Surender S.</span>
          </div>
        </div>

        <button className="mt-auto w-full group flex items-center justify-center gap-2 py-3 rounded-xl bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 font-bold uppercase tracking-widest text-xs border border-blue-500/20 transition-all">
          View Contractor Details
          <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
        </button>
      </motion.div>

      {/* Contractor Beta */}
      <motion.div 
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
        className="glass-panel p-6 border-t-4 border-t-yellow-500 relative overflow-hidden flex flex-col"
      >
        <div className="absolute top-0 right-0 p-6 opacity-5 pointer-events-none">
          <ShieldAlert className="w-48 h-48 text-yellow-500" />
        </div>
        
        <div className="flex justify-between items-start mb-6 relative z-10">
          <div>
            <h2 className="text-2xl font-black text-white tracking-wide flex items-center gap-2">
              Contractor Beta
              <span className="px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 text-[9px] uppercase tracking-widest">Yellow PPE</span>
            </h2>
            <div className="text-sm text-gray-400 mt-1 font-medium">Heavy Machinery</div>
          </div>
          <div className="text-right">
            <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold">Safety Score</span>
            <div className="text-3xl font-black text-warning mt-1">84</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-6 relative z-10">
          <MetricItem label="Workers" value="65" icon={Users} colorClass="yellow-400" />
          <MetricItem label="Present (Live)" value={realTimeStats.yellowCount || 54} icon={UserCheck} colorClass="success" />
          <MetricItem label="PPE Compliance" value="88%" icon={HardHat} colorClass="yellow-400" />
          <MetricItem label="PPE Violations" value="8" icon={AlertTriangle} colorClass="warning" highlight={true} />
          <MetricItem label="Zone Breaches" value="4" icon={ShieldCheck} colorClass="danger" highlight={true} />
          <div className="flex items-center justify-between p-3 rounded-lg border bg-background/40 border-foreground/5">
            <span className="text-xs text-muted-foreground uppercase font-bold tracking-wider">Supervisor</span>
            <span className="font-bold text-sm text-white truncate max-w-[100px]" title="Rajesh Kumar">Rajesh K.</span>
          </div>
        </div>

        <button className="mt-auto w-full group flex items-center justify-center gap-2 py-3 rounded-xl bg-yellow-500/10 hover:bg-yellow-500/20 text-yellow-400 font-bold uppercase tracking-widest text-xs border border-yellow-500/20 transition-all">
          View Contractor Details
          <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
        </button>
      </motion.div>
    </div>
  );
}

