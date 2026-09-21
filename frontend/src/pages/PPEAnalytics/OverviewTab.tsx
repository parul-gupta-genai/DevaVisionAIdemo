import React, { useMemo } from 'react';
import { Users, ShieldAlert, AlertTriangle, Activity } from 'lucide-react';
import { useCameraStateStore } from '@/store/useCameraStateStore';
import { cn } from '@/utils/utils';

export default function OverviewTab() {
  const { states } = useCameraStateStore();

  const realTimeStats = useMemo(() => {
    let blueCount = 0;
    let yellowCount = 0;
    let missingCount = 0;
    Object.values(states).forEach((state: any) => {
      const ppeEvents = state.events?.PPEDetectionPlugin || [];
      const statsEvent = ppeEvents.find((e: any) => e.event_type === "PPE_STATS");
      if (statsEvent?.metadata) {
        blueCount += statsEvent.metadata.contractor_1_count || 0;
        yellowCount += statsEvent.metadata.contractor_2_count || 0;
        missingCount += statsEvent.metadata.missing_ppe_count || 0;
      }
    });
    return { blueCount, yellowCount, missingCount };
  }, [states]);

  const totalLabour = realTimeStats.blueCount + realTimeStats.yellowCount + realTimeStats.missingCount;
  const complianceRate = totalLabour > 0 
    ? Math.round(((realTimeStats.blueCount + realTimeStats.yellowCount) / totalLabour) * 100) 
    : 0;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <KPICard 
          title="Total Active Labour" 
          value={totalLabour.toString()} 
          icon={<Users className="w-6 h-6 text-blue-400" />} 
          trend={totalLabour > 0 ? "Live tracking" : "No active labour"}
        />
        <KPICard 
          title="Overall Compliance" 
          value={totalLabour > 0 ? `${complianceRate}%` : "—"} 
          icon={<ShieldAlert className="w-6 h-6 text-success" />} 
          trend="Target: 100%"
          valueColor={totalLabour > 0 && complianceRate < 90 ? "text-danger" : "text-success"}
        />
        <KPICard 
          title="Safety Violations" 
          value={realTimeStats.missingCount.toString()} 
          icon={<AlertTriangle className="w-6 h-6 text-danger" />} 
          trend={realTimeStats.missingCount > 0 ? "Active Warnings" : "No violations"}
          valueColor={realTimeStats.missingCount > 0 ? "text-danger" : "text-white"}
        />
        <KPICard 
          title="Site Activity" 
          value={totalLabour > 10 ? "High" : totalLabour > 0 ? "Normal" : "Idle"} 
          icon={<Activity className="w-6 h-6 text-indigo-400" />} 
          trend={totalLabour > 0 ? "Active Monitoring" : "Standby"}
        />
      </div>

      <div className="glass-panel p-6 mt-8">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-bold text-white">Compliance Trend (24h)</h3>
          <button className="text-sm text-primary hover:text-primary-400 transition-colors">Export Report</button>
        </div>
        <div className="h-64 w-full flex items-center justify-center border border-dashed border-zinc-700 rounded-lg">
          <span className="text-zinc-500">Historical compliance API unavailable</span>
        </div>
      </div>
    </div>
  );
}

function KPICard({ title, value, icon, trend, valueColor = "text-white" }: any) {
  return (
    <div className="glass-panel p-5 hover:bg-white/[0.02] transition-colors relative overflow-hidden group">
      <div className="absolute top-0 right-0 w-24 h-24 bg-foreground/5 rounded-full blur-2xl -mr-10 -mt-10 group-hover:bg-primary/10 transition-colors" />
      <div className="flex justify-between items-start mb-4">
        <div className="p-2 bg-background/40 rounded-lg border border-foreground/5">
          {icon}
        </div>
        <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">{title}</span>
      </div>
      <div className="flex flex-col gap-1">
        <span className={cn("text-3xl font-black tracking-tight", valueColor)}>{value}</span>
        <span className="text-xs text-gray-400 font-medium">{trend}</span>
      </div>
    </div>
  )
}
