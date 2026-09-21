import { memo, useState, useEffect, useMemo } from 'react'
import { X, Activity, Cpu, Zap, Box, Hash, Shield, HardHat, Users, Car, Package, AlertTriangle, CheckCircle2, Sparkles, Sliders, Gauge } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '@/api/api'
import { cn } from '@/utils/utils'
import { useCameraStateStore } from '@/store/useCameraStateStore'

const PLUGIN_METRICS: Record<string, any> = {
  "VisitorPlugin": { label: "Visitor & VIP", cost: "Medium", cpu: "8%", gpu: "15%", latency: "+20ms", mem: "100MB", version: "v2.0" },
  "PPEDetectionPlugin": { label: "PPE Safety (Helmet/Vest)", cost: "High", cpu: "15%", gpu: "30%", latency: "+35ms", mem: "180MB", version: "v1.5" },
  "FireDetectionPlugin": { label: "Fire & Smoke", cost: "Low", cpu: "4%", gpu: "10%", latency: "+3ms", mem: "25MB", version: "v2.0" },
  "FightDetectionPlugin": { label: "Fight / Quarrel", cost: "Low", cpu: "1%", gpu: "5%", latency: "+1ms", mem: "2MB", version: "v1.0" },
  "ANPRPlugin": { label: "ANPR Number Plate", cost: "High", cpu: "12%", gpu: "25%", latency: "+40ms", mem: "150MB", version: "v2.1" },
  "ParkingAnalyticsPlugin": { label: "Parking Management", cost: "Low", cpu: "3%", gpu: "5%", latency: "+5ms", mem: "20MB", version: "v1.0" },
  "IntrusionDetectionPlugin": { label: "Intrusion & Night Theft", cost: "Medium", cpu: "6%", gpu: "10%", latency: "+12ms", mem: "45MB", version: "v1.4" },
  "PeopleCountingPlugin": { label: "People Counting (In/Out)", cost: "Low", cpu: "2%", gpu: "5%", latency: "+4ms", mem: "15MB", version: "v1.2" },
  "AttendanceDetectionPlugin": { label: "Face Attendance AI", cost: "Medium", cpu: "8%", gpu: "15%", latency: "+25ms", mem: "80MB", version: "v3.0" },
  "CartonCountingPlugin": { label: "Material & Box Counting", cost: "Low", cpu: "0.5%", gpu: "1%", latency: "+1ms", mem: "5MB", version: "v1.0" },
  "RestrictionZonePlugin": { label: "Restricted Zone Polygon", cost: "Low", cpu: "1%", gpu: "5%", latency: "+2ms", mem: "10MB", version: "v1.0" },
};

const PRESETS = [
  {
    id: 'gate',
    label: 'Main Gate & Entry',
    icon: Car,
    plugins: ['ANPRPlugin', 'VisitorPlugin', 'PeopleCountingPlugin'],
    fps: '15'
  },
  {
    id: 'attendance',
    label: 'Face Attendance & Staff',
    icon: Users,
    plugins: ['AttendanceDetectionPlugin', 'PeopleCountingPlugin', 'VisitorPlugin'],
    fps: '15'
  },
  {
    id: 'material_yard',
    label: 'Material Yard & Night Theft',
    icon: Package,
    plugins: ['IntrusionDetectionPlugin', 'RestrictionZonePlugin', 'CartonCountingPlugin'],
    fps: '10'
  },
  {
    id: 'construction',
    label: 'Construction & PPE Safety',
    icon: HardHat,
    plugins: ['PPEDetectionPlugin', 'FireDetectionPlugin', 'IntrusionDetectionPlugin'],
    fps: '10'
  },
  {
    id: 'all',
    label: 'All Active Security',
    icon: Shield,
    plugins: ['IntrusionDetectionPlugin', 'FightDetectionPlugin', 'FireDetectionPlugin'],
    fps: '15'
  },
];

const CATEGORIES = [
  { id: 'security', label: 'Security & Anti-Theft', icon: Shield, plugins: ["IntrusionDetectionPlugin", "RestrictionZonePlugin", "FightDetectionPlugin"] },
  { id: 'safety', label: 'Safety & PPE', icon: HardHat, plugins: ["PPEDetectionPlugin", "FireDetectionPlugin"] },
  { id: 'people', label: 'People & Attendance', icon: Users, plugins: ["AttendanceDetectionPlugin", "PeopleCountingPlugin", "VisitorPlugin"] },
  { id: 'vehicles', label: 'Vehicles & ANPR', icon: Car, plugins: ["ANPRPlugin", "ParkingAnalyticsPlugin"] },
  { id: 'materials', label: 'Materials & Boxes', icon: Package, plugins: ["CartonCountingPlugin"] },
];

export const PluginManagerModal = memo(({ cameraId, isOpen, onClose }: { cameraId: string, isOpen: boolean, onClose: () => void }) => {
  const [allowedPlugins, setAllowedPlugins] = useState<string[]>([]);
  const [targetFps, setTargetFps] = useState<string>('15');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!isOpen) return;
    setIsLoading(true);
    api.get(`/api/config?t=${Date.now()}`)
      .then(res => res.data)
      .then(data => {
        const plugins = data?.CAMERA_PLUGINS?.[cameraId];
        if (plugins && Array.isArray(plugins)) {
          setAllowedPlugins(plugins);
        } else {
          setAllowedPlugins([]);
        }
        if (data?.CAMERA_FPS?.[cameraId]) {
          setTargetFps(String(data.CAMERA_FPS[cameraId]));
        }
      })
      .catch(err => {
        console.error("Failed to fetch config plugins:", err);
        setAllowedPlugins([]);
      })
      .finally(() => setIsLoading(false));
  }, [cameraId, isOpen]);

  const saveConfig = (newPlugins: string[], newFps?: string) => {
    setAllowedPlugins(newPlugins);
    useCameraStateStore.getState().setCameraPlugins(cameraId, newPlugins);

    const updates: Record<string, any> = {
      CAMERA_PLUGINS: { [cameraId]: newPlugins }
    };
    if (newFps) {
      updates.CAMERA_FPS = { [cameraId]: parseInt(newFps, 10) };
    }

    api.post('/api/config', { updates }).catch(err => {
      console.error("Failed to persist plugin update:", err);
    });
  };

  const togglePlugin = (pluginName: string) => {
    let newPlugins = [...allowedPlugins];
    if (newPlugins.includes(pluginName)) {
      newPlugins = newPlugins.filter(p => p !== pluginName);
    } else {
      newPlugins.push(pluginName);
    }
    saveConfig(newPlugins, targetFps);
  };

  const applyPreset = (preset: typeof PRESETS[0]) => {
    setTargetFps(preset.fps);
    saveConfig(preset.plugins, preset.fps);
  };

  const handleFpsChange = (fps: string) => {
    setTargetFps(fps);
    saveConfig(allowedPlugins, fps);
  };

  const currentGpuLoad = useMemo(() => {
    return allowedPlugins.reduce((acc, p) => {
      const gpuStr = PLUGIN_METRICS[p]?.gpu || "0%";
      return acc + parseFloat(gpuStr.replace('%', ''));
    }, 0);
  }, [allowedPlugins]);

  const isOverloaded = currentGpuLoad > 85;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-md" onClick={onClose}>
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        onClick={e => e.stopPropagation()}
        className="w-full max-w-4xl bg-slate-900 border border-slate-700 shadow-2xl rounded-2xl overflow-hidden flex flex-col max-h-[92vh] text-slate-100"
      >
        {/* Header */}
        <div className="p-5 border-b border-slate-800 flex justify-between items-center bg-slate-950/80">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Zap className="w-6 h-6 text-amber-400" />
              Camera AI & Performance Manager
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Select AI Modules and Processing FPS for <span className="text-cyan-400 font-mono font-semibold">{cameraId}</span>
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-xl transition-colors text-slate-400 hover:text-white">
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto p-6 space-y-6 flex-1 bg-slate-900/90 custom-scrollbar">
          
          {/* 1-Click Fast Presets */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-wider">
              <Sparkles className="w-4 h-4 text-amber-400" />
              Quick Camera Presets (एक-क्लिक में सेटअप)
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
              {PRESETS.map(preset => (
                <button
                  key={preset.id}
                  onClick={() => applyPreset(preset)}
                  className="flex flex-col items-center text-center p-2.5 rounded-xl border border-slate-800 bg-slate-800/40 hover:bg-slate-800 hover:border-amber-500/40 text-slate-300 hover:text-white transition-all group shadow-xs"
                >
                  <preset.icon className="w-5 h-5 text-amber-400 mb-1 group-hover:scale-110 transition-transform" />
                  <span className="text-xs font-bold line-clamp-1">{preset.label}</span>
                  <span className="text-[10px] text-slate-500 font-mono mt-0.5">{preset.fps} FPS · {preset.plugins.length} AI</span>
                </button>
              ))}
            </div>
          </div>

          {/* Camera FPS & Processing Rate Control */}
          <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                <Gauge className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-white">Camera AI Frame Rate (FPS)</h4>
                <p className="text-xs text-slate-400">Lower FPS saves GPU power & bandwidth for multi-camera deployments.</p>
              </div>
            </div>

            <div className="flex items-center gap-1.5 bg-slate-900 p-1 rounded-xl border border-slate-800">
              {[
                { val: '10', label: '10 FPS', badge: 'Eco (6+ Cams)' },
                { val: '15', label: '15 FPS', badge: 'Recommended' },
                { val: '20', label: '20 FPS', badge: 'Fast' },
                { val: '30', label: '30 FPS', badge: 'Max' }
              ].map(f => (
                <button
                  key={f.val}
                  onClick={() => handleFpsChange(f.val)}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex flex-col items-center",
                    targetFps === f.val 
                      ? "bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20" 
                      : "text-slate-400 hover:text-white hover:bg-slate-800"
                  )}
                >
                  <span>{f.label}</span>
                  <span className={cn("text-[9px] font-normal", targetFps === f.val ? "text-slate-900 font-semibold" : "text-slate-500")}>
                    {f.badge}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Granular AI Plugins Checkboxes */}
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-wider">
              <Sliders className="w-4 h-4 text-cyan-400" />
              Individual AI Analytics Modules (चालू / बंद करें)
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
              {CATEGORIES.map(category => (
                <div key={category.id} className="space-y-2.5 bg-slate-950/40 p-3.5 rounded-xl border border-slate-800/80">
                  <h3 className="text-xs font-bold text-slate-300 flex items-center gap-2 border-b border-slate-800 pb-2">
                    <category.icon className="w-4 h-4 text-cyan-400" />
                    {category.label}
                  </h3>
                  <div className="space-y-1.5">
                    {category.plugins.map(plugin => {
                      const metrics = PLUGIN_METRICS[plugin];
                      if (!metrics) return null;
                      const active = allowedPlugins.includes(plugin);

                      return (
                        <div 
                          key={plugin} 
                          onClick={() => togglePlugin(plugin)} 
                          className={cn(
                            "p-2.5 rounded-lg border transition-all duration-200 cursor-pointer flex justify-between items-center select-none",
                            active 
                              ? "bg-cyan-950/40 border-cyan-500/40 shadow-[0_0_12px_rgba(6,182,212,0.1)] text-white" 
                              : "bg-slate-900/60 border-slate-800/80 hover:bg-slate-800/60 text-slate-400"
                          )}
                        >
                          <div className="flex items-center gap-2.5">
                            <div className={cn(
                              "w-4 h-4 rounded flex items-center justify-center border transition-colors",
                              active ? "bg-cyan-500 border-cyan-400 text-slate-950" : "border-slate-700 bg-slate-800"
                            )}>
                              {active && <CheckCircle2 className="w-3.5 h-3.5 stroke-[3]" />}
                            </div>
                            <span className={cn("text-xs font-semibold", active ? "text-cyan-200" : "text-slate-400")}>
                              {metrics.label}
                            </span>
                          </div>
                          <div className="text-[10px] font-mono font-bold text-slate-500 bg-slate-800/80 px-1.5 py-0.5 rounded border border-slate-700/50">
                            GPU {metrics.gpu}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* Footer & Estimated Hardware Load */}
        <div className="p-5 bg-slate-950 border-t border-slate-800 flex flex-col gap-3">
          <div className="flex justify-between items-center text-xs">
            <span className="font-bold text-slate-300 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-cyan-400" />
              Estimated Single Camera AI Load
            </span>
            <span className={cn(
              "font-mono font-bold text-sm",
              isOverloaded ? "text-rose-400" : currentGpuLoad > 60 ? "text-amber-400" : "text-emerald-400"
            )}>
              {currentGpuLoad}% GPU Compute
            </span>
          </div>
          
          <div className="h-2.5 bg-slate-900 rounded-full overflow-hidden border border-slate-800 shadow-inner">
            <motion.div 
              className={cn("h-full transition-all duration-300", isOverloaded ? "bg-rose-500" : currentGpuLoad > 60 ? "bg-amber-400" : "bg-emerald-400")}
              style={{ width: `${Math.min(currentGpuLoad, 100)}%` }}
            />
          </div>

          <div className="flex flex-col sm:flex-row justify-between items-center gap-2 text-xs">
            {isOverloaded ? (
              <div className="flex items-center gap-1.5 text-rose-400 font-semibold bg-rose-950/30 px-2.5 py-1 rounded-md border border-rose-800/40">
                <AlertTriangle className="w-3.5 h-3.5" />
                High load detected. We recommend 10 or 15 FPS for multiple cameras.
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-emerald-400 font-semibold bg-emerald-950/30 px-2.5 py-1 rounded-md border border-emerald-800/40">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Optimal profile for smooth multi-camera analytics
              </div>
            )}
            
            <button
              onClick={onClose}
              className="px-5 py-2 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-bold rounded-xl shadow-lg transition-all text-xs"
            >
              Done / Apply Settings
            </button>
          </div>
        </div>

      </motion.div>
    </div>
  );
});
PluginManagerModal.displayName = 'PluginManagerModal';
