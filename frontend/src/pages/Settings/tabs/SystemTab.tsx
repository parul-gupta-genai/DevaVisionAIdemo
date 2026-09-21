import React from 'react'
import { HardDrive, Server, Activity } from 'lucide-react'

export function SystemTab() {
  return (
    <div className="relative z-10 space-y-6">
      <div className="flex items-center gap-3 mb-8">
        <Server className="w-6 h-6 text-primary" />
        <h2 className="text-xl font-bold text-white tracking-wide">System Performance</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl opacity-70">
        <div className="bg-background/40 p-4 rounded-xl border border-foreground/5">
          <div className="font-bold text-sm text-white mb-2 flex items-center gap-2">
            <Activity className="w-4 h-4 text-emerald-400" /> GPU Performance Profile
          </div>
          <select className="bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm w-full">
            <option>Max Performance (Orin NX Default)</option>
            <option>Power Saver</option>
          </select>
        </div>
        <div className="bg-background/40 p-4 rounded-xl border border-foreground/5">
          <div className="font-bold text-sm text-white mb-2 flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-blue-400" /> Logging Level
          </div>
          <select className="bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm w-full">
            <option>Info (Default)</option>
            <option>Debug (Verbose)</option>
            <option>Warning Only</option>
          </select>
        </div>
      </div>
      <p className="text-xs text-muted-foreground mt-4 italic">Services management requires CLI access.</p>
    </div>
  )
}
