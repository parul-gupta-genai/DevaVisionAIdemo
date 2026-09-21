import React, { useState } from 'react';
import { 
  AlertTriangle, 
  Clock, 
  ShieldAlert, 
  Moon, 
  Truck, 
  Layers, 
  Send, 
  Volume2, 
  Eye, 
  CheckCircle2, 
  Radio, 
  Filter 
} from 'lucide-react';
import { cn } from '@/utils/utils';

export interface AntiTheftAlert {
  id: string;
  title: string;
  category: 'Night Theft' | 'Unauthorized Exit' | 'Stock Discrepancy' | 'Perimeter Breach';
  severity: 'Critical' | 'High' | 'Medium';
  message: string;
  cameraName: string;
  cameraId: string;
  timestamp: string;
  snapshotUrl: string;
  vehicleNumber?: string;
  materialInvolved: string;
  quantity: string;
  isResolved: boolean;
}

const MOCK_THEFT_ALERTS: AntiTheftAlert[] = [
  {
    id: 'ALT-THEFT-01',
    title: '🚨 After-Hours Movement in Central Steel Yard',
    category: 'Night Theft',
    severity: 'Critical',
    message: 'Motion & human silhouette detected moving 16mm TMT Rebars at 02:40 AM (Store Closed Hours: 08:00 PM - 06:00 AM). No authorized gate pass exists.',
    cameraName: 'CCTV-04 (Yard #2 Night Vision PTZ)',
    cameraId: 'CAM-YARD-04',
    timestamp: '2026-09-10T02:40:15',
    snapshotUrl: 'https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=800&auto=format&fit=crop',
    materialInvolved: 'Tata Tiscon 550D TMT Rebar',
    quantity: '~8 Bundles (Estimated)',
    isResolved: false
  },
  {
    id: 'ALT-THEFT-02',
    title: '🚜 Vehicle Outbound Without Valid Gate-Pass',
    category: 'Unauthorized Exit',
    severity: 'High',
    message: 'Tractor trailer (HR26 DK 8921) crossed Outbound Line-2 loaded with 40 Cement Bags with NO registered digital gate pass in the system.',
    cameraName: 'Gate-02 ANPR & Boom Barrier Cam',
    cameraId: 'CAM-GATE-02',
    timestamp: '2026-09-10T13:15:00',
    snapshotUrl: 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=800&auto=format&fit=crop',
    vehicleNumber: 'HR26 DK 8921',
    materialInvolved: 'UltraTech OPC 53 Cement',
    quantity: '40 Bags',
    isResolved: false
  },
  {
    id: 'ALT-THEFT-03',
    title: '⚠️ Unloading Count Discrepancy (Shrinkage Alert)',
    category: 'Stock Discrepancy',
    severity: 'High',
    message: 'Delivery Bill (CH-89234) indicated 500 Bags, but CCTV AI Tripwire Counter recorded only 460 Bags unloaded into the warehouse (Discrepancy: -40 Bags missing).',
    cameraName: 'Bay-01 Unloading Overhead AI Cam',
    cameraId: 'CAM-BAY-01',
    timestamp: '2026-09-09T16:20:00',
    snapshotUrl: 'https://images.unsplash.com/photo-1607344645866-009c320b5ab8?w=800&auto=format&fit=crop',
    materialInvolved: 'UltraTech OPC 53 Grade Cement',
    quantity: '40 Bags Short',
    isResolved: true
  },
  {
    id: 'ALT-THEFT-04',
    title: '🚶 Perimeter Fence Climbing & Material Toss',
    category: 'Perimeter Breach',
    severity: 'Critical',
    message: 'Person detected near East Boundary Wall tossing copper electrical cable coils outside site perimeter into an idling vehicle.',
    cameraName: 'Perimeter East Cam #08 (Thermal IR)',
    cameraId: 'CAM-PERI-08',
    timestamp: '2026-09-08T23:10:00',
    snapshotUrl: 'https://images.unsplash.com/photo-1581094794329-c8112a89af12?w=800&auto=format&fit=crop',
    materialInvolved: 'Finolex Copper Armoured Cable',
    quantity: '3 Coils (~150m)',
    isResolved: true
  }
];

export default function AlertsTab() {
  const [alerts, setAlerts] = useState<AntiTheftAlert[]>(MOCK_THEFT_ALERTS);
  const [selectedFilter, setSelectedFilter] = useState<string>('ALL');

  const filteredAlerts = alerts.filter(a => {
    if (selectedFilter === 'CRITICAL') return a.severity === 'Critical';
    if (selectedFilter === 'THEFT') return a.category === 'Night Theft' || a.category === 'Perimeter Breach';
    if (selectedFilter === 'UNAUTHORIZED') return a.category === 'Unauthorized Exit';
    if (selectedFilter === 'DISCREPANCY') return a.category === 'Stock Discrepancy';
    return true;
  });

  const triggerEmergencySiren = (alertItem: AntiTheftAlert) => {
    alert(`🚨 EMERGENCY SECURITY ESCALATION DISPATCHED!\n\nAlert: ${alertItem.title}\nCamera: ${alertItem.cameraName}\nMaterial: ${alertItem.materialInvolved} (${alertItem.quantity})\n\n📢 Siren Triggered on Gate-01 & Gate-02\n📱 WhatsApp High-Priority SOS sent to Site Security In-Charge & Head Office!`);
  };

  const markResolved = (id: string) => {
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, isResolved: !a.isResolved } : a));
  };

  return (
    <div className="space-y-6">
      {/* Header & Filter Bar */}
      <div className="glass border border-foreground/10 rounded-2xl p-6 shadow-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-rose-400 animate-pulse" /> Material Anti-Theft & Pilferage Control Center
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            24x7 AI Surveillance for After-Hours Yard Theft, Gate-Pass Breaches, and Material Discrepancies
          </p>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          {['ALL', 'CRITICAL', 'THEFT', 'UNAUTHORIZED', 'DISCREPANCY'].map((f) => (
            <button
              key={f}
              onClick={() => setSelectedFilter(f)}
              className={cn(
                'px-3 py-1.5 rounded-xl text-xs font-bold transition-all',
                selectedFilter === f
                  ? 'bg-rose-500 text-white shadow-lg shadow-rose-500/20 scale-105'
                  : 'bg-foreground/10 text-muted-foreground hover:text-white hover:bg-foreground/20'
              )}
            >
              {f === 'ALL' ? 'All Alerts' : f === 'CRITICAL' ? '🚨 Critical' : f === 'THEFT' ? '🌙 Night Theft' : f === 'UNAUTHORIZED' ? '🚜 No Gate-Pass' : '⚠️ Discrepancy'}
            </button>
          ))}
        </div>
      </div>

      {/* Alerts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {filteredAlerts.map(item => (
          <div 
            key={item.id} 
            className={cn(
              "glass border rounded-2xl overflow-hidden shadow-xl p-5 flex flex-col justify-between transition-all space-y-4",
              item.severity === 'Critical' ? "border-rose-500/40 bg-rose-500/5 hover:border-rose-500/70" : "border-amber-500/30 bg-amber-500/5 hover:border-amber-500/50"
            )}
          >
            {/* Top Row */}
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className={cn(
                  "p-2.5 rounded-xl text-white shrink-0 mt-0.5 shadow-md",
                  item.category === 'Night Theft' ? "bg-rose-600 shadow-rose-600/30" :
                  item.category === 'Unauthorized Exit' ? "bg-orange-600 shadow-orange-600/30" :
                  "bg-amber-600 shadow-amber-600/30"
                )}>
                  {item.category === 'Night Theft' ? <Moon className="w-5 h-5" /> :
                   item.category === 'Unauthorized Exit' ? <Truck className="w-5 h-5" /> :
                   <AlertTriangle className="w-5 h-5" />}
                </div>
                <div>
                  <h3 className="font-extrabold text-sm text-white">{item.title}</h3>
                  <div className="flex flex-wrap items-center gap-2 mt-1 text-[11px] text-muted-foreground">
                    <span className="font-mono text-primary/90">{item.cameraName}</span>
                    <span>•</span>
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {new Date(item.timestamp).toLocaleString()}</span>
                  </div>
                </div>
              </div>

              <span className={cn(
                "px-2.5 py-0.5 rounded-full text-[10px] font-extrabold border shrink-0",
                item.severity === 'Critical' ? "bg-rose-500/20 text-rose-400 border-rose-500/40 animate-pulse" : "bg-amber-500/20 text-amber-300 border-amber-500/40"
              )}>
                {item.severity} Priority
              </span>
            </div>

            {/* Description & Proof Snapshot */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-black/40 p-3 rounded-xl border border-foreground/10">
              <div className="relative rounded-lg overflow-hidden h-28 sm:h-auto border border-foreground/20">
                <img src={item.snapshotUrl} alt="CCTV Theft Snapshot" className="w-full h-full object-cover" />
                <div className="absolute bottom-1 left-1 bg-black/80 px-2 py-0.5 rounded text-[9px] font-mono text-rose-400 font-bold">
                  CCTV PROOF
                </div>
              </div>

              <div className="sm:col-span-2 space-y-1.5 flex flex-col justify-center text-xs">
                <p className="text-muted-foreground text-[11px] leading-relaxed">{item.message}</p>
                <div className="grid grid-cols-2 gap-2 pt-1 border-t border-foreground/10 text-[11px]">
                  <div>
                    <span className="text-muted-foreground block text-[10px]">Material Involved</span>
                    <span className="font-bold text-white truncate block">{item.materialInvolved}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[10px]">Quantity / Loss</span>
                    <span className="font-bold text-rose-400 font-mono block">{item.quantity}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Bar */}
            <div className="flex items-center justify-between pt-2 border-t border-foreground/10 gap-2">
              <button
                type="button"
                onClick={() => markResolved(item.id)}
                className={cn(
                  "px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all",
                  item.isResolved
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : "bg-foreground/10 text-muted-foreground hover:text-white"
                )}
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                {item.isResolved ? "Resolved & Logged ✅" : "Mark as Investigated"}
              </button>

              <button
                type="button"
                onClick={() => triggerEmergencySiren(item)}
                className="px-4 py-1.5 rounded-xl bg-gradient-to-r from-rose-500 to-red-600 hover:from-rose-600 hover:to-red-700 text-white font-extrabold text-xs shadow-lg shadow-rose-500/20 flex items-center gap-1.5 active:scale-95 transition-all"
              >
                <Volume2 className="w-3.5 h-3.5" /> Trigger Siren & WhatsApp SOS 🚨
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

