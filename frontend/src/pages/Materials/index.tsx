import React, { useState } from 'react';
import { Box, LayoutDashboard, History, BellRing, Activity, FileText } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/utils/utils';

import OverviewTab from './OverviewTab';
import LiveTrackingTab from './LiveTrackingTab';
import HistoryTab from './HistoryTab';
import ReportsTab from './ReportsTab';
import AlertsTab from './AlertsTab';

const tabs = [
  { id: 'overview', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'live', label: 'Live Tracking', icon: Activity },
  { id: 'history', label: 'History', icon: History },
  { id: 'reports', label: 'Inventory Reports', icon: FileText },
  { id: 'alerts', label: 'Alerts', icon: BellRing },
];

export default function Materials() {
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <div className="h-full w-full p-2 md:p-8 overflow-y-auto custom-scrollbar">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl md:text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-orange-600 mb-2 tracking-tight flex items-center gap-3">
              <Box className="w-8 h-8 text-amber-500" />
              Material Tracking
            </h1>
            <p className="text-muted-foreground font-medium text-sm">
              Construction site materials: Cement, Steel, Pipes, Cartons, and Equipment.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-success/20 border border-success/30 text-success text-xs font-bold uppercase tracking-wider">
              <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
              Live Processing
            </span>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-2 border-b border-foreground/10 pb-4 overflow-x-auto custom-scrollbar">
          {tabs.map(tab => {
            const isActive = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all relative shrink-0",
                  isActive ? "text-primary bg-primary/10 border border-primary/20" : "text-muted-foreground hover:bg-foreground/5 hover:text-white"
                )}
              >
                <Icon className={cn("w-4 h-4", isActive ? "text-primary drop-shadow-md" : "")} />
                {tab.label}
              </button>
            )
          })}
        </div>

        {/* Tab Content */}
        <div className="pt-2 pb-10">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
            >
              {activeTab === 'overview' && <OverviewTab />}
              {activeTab === 'live' && <LiveTrackingTab />}
              {activeTab === 'history' && <HistoryTab />}
              {activeTab === 'reports' && <ReportsTab />}
              {activeTab === 'alerts' && <AlertsTab />}
            </motion.div>
          </AnimatePresence>
        </div>

      </div>
    </div>
  );
}
