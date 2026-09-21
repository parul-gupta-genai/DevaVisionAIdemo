import React, { useState } from 'react';
import { Users, LayoutDashboard, UserPlus, Video, History, Eye } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/utils/utils';

import DashboardTab from './DashboardTab';
import RegisterTab from './RegisterTab';
import LiveVisitsTab from './LiveVisitsTab';
import HistoryTab from './HistoryTab';
import WatchlistTab from './WatchlistTab';

const tabs = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'register', label: 'Register', icon: UserPlus },
  { id: 'live', label: 'Live Visits', icon: Video },
  { id: 'history', label: 'Day-Wise History', icon: History },
  { id: 'watchlist', label: 'Watchlist', icon: Eye },
];

export default function Visitors() {
  const [activeTab, setActiveTab] = useState('dashboard');

  return (
    <div className="h-full w-full p-2 md:p-8 overflow-y-auto custom-scrollbar">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl md:text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-600 mb-2 tracking-tight flex items-center gap-3">
              <Users className="w-8 h-8 text-blue-500" />
              Visitor Management
            </h1>
            <p className="text-muted-foreground font-medium text-sm">
              Unified workflow: Registration, Live Tracking, and Access Control.
            </p>
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
                  isActive ? "text-primary bg-primary/10 border border-primary/20 font-semibold" : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground dark:hover:text-white"
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
              {activeTab === 'dashboard' && <DashboardTab />}
              {activeTab === 'register' && <RegisterTab />}
              {activeTab === 'live' && <LiveVisitsTab />}
              {activeTab === 'history' && <HistoryTab />}
              {activeTab === 'watchlist' && <WatchlistTab />}
            </motion.div>
          </AnimatePresence>
        </div>

      </div>
    </div>
  );
}
