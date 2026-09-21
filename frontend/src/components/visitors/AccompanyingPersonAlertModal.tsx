import React from 'react';
import { ShieldAlert, UserCheck, UserX, AlertTriangle, Camera, Clock, CheckCircle2, XCircle } from 'lucide-react';

export interface AccompanyingAlertData {
  visit_id: string;
  visitor_id: string;
  visitor_name: string;
  expected_accompanying_persons: number;
  detected_accompanying_persons: number;
  additional_person_count: number;
  validation_status: string; // UNREGISTERED_ACCOMPANYING_PERSON | EXTRA_VISITOR_DETECTED
  camera_id: string;
  timestamp: string;
  snapshot_url?: string;
  tracking_ids?: string[];
}

interface Props {
  alert: AccompanyingAlertData | null;
  isOpen: boolean;
  onClose: () => void;
  onAction: (action: 'ALLOW' | 'REQUIRE_REGISTRATION' | 'SECURITY_ESCORT') => void;
}

export const AccompanyingPersonAlertModal: React.FC<Props> = ({ alert, isOpen, onClose, onAction }) => {
  if (!isOpen || !alert) return null;

  const isUnregistered = alert.validation_status === 'UNREGISTERED_ACCOMPANYING_PERSON';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-2xl bg-slate-900/90 border border-amber-500/40 rounded-2xl shadow-2xl shadow-amber-500/10 overflow-hidden text-slate-100">
        
        {/* Header Banner */}
        <div className="bg-gradient-to-r from-amber-600 via-orange-600 to-red-600 p-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-white/20 rounded-xl backdrop-blur-sm">
              <ShieldAlert className="w-7 h-7 text-white animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 text-xs font-bold bg-white text-red-700 rounded-full uppercase tracking-wide">
                  Action Required
                </span>
                <span className="text-xs text-amber-100 font-mono">{alert.visit_id}</span>
              </div>
              <h2 className="text-xl font-bold text-white mt-1">
                {isUnregistered ? 'Unregistered Accompanying Person Detected' : 'Extra Visitor Detected'}
              </h2>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-white/80 hover:text-white hover:bg-white/10 transition-colors"
          >
            <XCircle className="w-6 h-6" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6">
          
          {/* Visitor & Gate Match Card */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            
            {/* Primary Visitor Info */}
            <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4 space-y-2">
              <div className="text-xs font-semibold text-amber-400 uppercase tracking-wider">Registered Primary Visitor</div>
              <div className="text-lg font-bold text-white">{alert.visitor_name}</div>
              <div className="text-xs text-slate-400 font-mono">ID: {alert.visitor_id}</div>
              <div className="flex items-center gap-4 text-xs text-slate-300 mt-2">
                <div>Expected Companions: <span className="font-bold text-emerald-400">{alert.expected_accompanying_persons}</span></div>
                <div>Total Registered: <span className="font-bold text-emerald-400">{1 + alert.expected_accompanying_persons}</span></div>
              </div>
            </div>

            {/* Vision Detection Result */}
            <div className="bg-slate-800/60 border border-amber-500/30 rounded-xl p-4 space-y-2">
              <div className="text-xs font-semibold text-amber-400 uppercase tracking-wider">Vision Detection Result</div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-extrabold text-amber-400">{alert.detected_accompanying_persons}</span>
                <span className="text-xs text-slate-400">Persons Detected at Gate ROI</span>
              </div>
              <div className="text-xs text-red-400 font-semibold flex items-center gap-1">
                <AlertTriangle className="w-4 h-4" />
                Additional Unregistered: <span className="underline font-bold">{alert.additional_person_count} Person(s)</span>
              </div>
              <div className="text-xs text-slate-400 font-mono mt-1">
                Track IDs: {alert.tracking_ids?.join(', ') || 'P001, P002'}
              </div>
            </div>

          </div>

          {/* Camera Snapshot / Evidence */}
          <div className="relative rounded-xl overflow-hidden bg-slate-950 border border-slate-800 aspect-video flex items-center justify-center group">
            {alert.snapshot_url ? (
              <img src={alert.snapshot_url} alt="Gate ROI Snapshot" className="w-full h-full object-cover" />
            ) : (
              <div className="flex flex-col items-center gap-2 text-slate-500">
                <Camera className="w-10 h-10 stroke-1" />
                <span className="text-xs font-mono">Live Gate ROI Frame Captured</span>
              </div>
            )}
            <div className="absolute top-3 left-3 bg-black/60 backdrop-blur-sm border border-white/10 px-3 py-1 rounded-lg text-xs font-mono text-slate-200 flex items-center gap-2">
              <Camera className="w-3.5 h-3.5 text-amber-400" /> {alert.camera_id}
            </div>
            <div className="absolute top-3 right-3 bg-black/60 backdrop-blur-sm border border-white/10 px-3 py-1 rounded-lg text-xs font-mono text-slate-200 flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-amber-400" /> {alert.timestamp}
            </div>
          </div>

          {/* Verification Actions */}
          <div className="space-y-3 pt-2">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider text-center">
              Operator Verification & Action
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <button
                onClick={() => onAction('ALLOW')}
                className="flex items-center justify-center gap-2 px-4 py-3 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold rounded-xl transition-all shadow-lg shadow-emerald-600/20 active:scale-95"
              >
                <UserCheck className="w-4 h-4" /> Allow Entry
              </button>
              <button
                onClick={() => onAction('REQUIRE_REGISTRATION')}
                className="flex items-center justify-center gap-2 px-4 py-3 bg-amber-600 hover:bg-amber-500 text-white text-sm font-semibold rounded-xl transition-all shadow-lg shadow-amber-600/20 active:scale-95"
              >
                <AlertTriangle className="w-4 h-4" /> Require Reg
              </button>
              <button
                onClick={() => onAction('SECURITY_ESCORT')}
                className="flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-500 text-white text-sm font-semibold rounded-xl transition-all shadow-lg shadow-red-600/20 active:scale-95"
              >
                <UserX className="w-4 h-4" /> Escort Security
              </button>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
};
