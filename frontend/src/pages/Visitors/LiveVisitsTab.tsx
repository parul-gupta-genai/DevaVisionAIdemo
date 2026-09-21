import React, { useEffect, useState } from 'react';
import { LogIn, LogOut, QrCode, Clock, Camera, UserCheck } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '@/utils/utils';
import { api } from '@/api/api';

export default function LiveVisitsTab() {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const res = await api.get('/api/plugins/visitor/events/all').catch(() => ({ data: [] }));
        setEvents(Array.isArray(res.data) ? res.data : []);
      } catch (err) {
        console.error("Failed to load live visits", err);
      } finally {
        setLoading(false);
      }
    };
    fetchEvents();
  }, []);

  const entries = events.filter(e => e.event_type === 'ENTRY');
  const exits = events.filter(e => e.event_type === 'EXIT');

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide">Live Entry & Exit Feed</h2>
          <p className="text-sm text-muted-foreground">Real-time monitoring of visitor movements.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-success/20 border border-success/30 text-success text-xs font-bold uppercase tracking-wider">
            <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
            Live Processing
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
        
        {/* Entries */}
        <div className="space-y-4">
          <h3 className="text-sm font-bold text-emerald-400 uppercase tracking-widest flex items-center gap-2 border-b border-foreground/10 pb-2">
            <LogIn className="w-4 h-4" /> Recent Entries
          </h3>
          
          <div className="space-y-4">
            {entries.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground text-sm glass rounded-2xl border border-foreground/5 flex flex-col items-center justify-center gap-2">
                <UserCheck className="w-8 h-8 opacity-40" />
                <span>No active entry events detected.</span>
              </div>
            ) : (
              entries.map((entry, idx) => (
                <motion.div 
                  key={entry.event_id || idx}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="glass border border-foreground/10 rounded-2xl overflow-hidden shadow-lg"
                >
                  <div className="p-4 bg-gradient-to-r from-emerald-500/10 to-transparent flex gap-4">
                    <div className="w-20 h-20 shrink-0 rounded-xl bg-background/50 border border-foreground/5 overflow-hidden flex items-center justify-center">
                      <div className="text-xs text-muted-foreground font-semibold">Photo</div>
                    </div>
                    
                    <div className="flex-1 min-w-0 flex flex-col justify-between">
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="text-xs text-emerald-400 font-bold uppercase tracking-wider mb-1">Visitor Detected</div>
                          <div className="font-black text-lg text-white truncate">{entry.visitor_name || entry.visitor_id || 'Visitor'}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-mono text-white bg-background/40 px-2 py-1 rounded-lg border border-foreground/5 inline-block">
                            {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex flex-wrap gap-x-4 gap-y-2 mt-2 text-xs">
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                          <Camera className="w-3.5 h-3.5" /> {entry.camera_id || 'Entry Camera'}
                        </div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))
            )}
          </div>
        </div>

        {/* Exits */}
        <div className="space-y-4">
          <h3 className="text-sm font-bold text-orange-400 uppercase tracking-widest flex items-center gap-2 border-b border-foreground/10 pb-2">
            <LogOut className="w-4 h-4" /> Recent Exits
          </h3>
          
          <div className="space-y-4">
            {exits.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground text-sm glass rounded-2xl border border-foreground/5 flex flex-col items-center justify-center gap-2">
                <Clock className="w-8 h-8 opacity-40" />
                <span>No active exit events detected.</span>
              </div>
            ) : (
              exits.map((exit, idx) => (
                <motion.div 
                  key={exit.event_id || idx}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="glass border border-foreground/10 rounded-2xl overflow-hidden shadow-lg"
                >
                  <div className="p-4 bg-gradient-to-r from-orange-500/10 to-transparent flex gap-4">
                    <div className="w-20 h-20 shrink-0 rounded-xl bg-background/50 border border-foreground/5 overflow-hidden flex items-center justify-center">
                      <div className="text-xs text-muted-foreground font-semibold">Photo</div>
                    </div>
                    
                    <div className="flex-1 min-w-0 flex flex-col justify-between">
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="text-xs text-orange-400 font-bold uppercase tracking-wider mb-1">Visitor Departed</div>
                          <div className="font-black text-lg text-white truncate">{exit.visitor_name || exit.visitor_id || 'Visitor'}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-mono text-white bg-background/40 px-2 py-1 rounded-lg border border-foreground/5 inline-block">
                            {exit.timestamp ? new Date(exit.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex flex-wrap gap-x-4 gap-y-2 mt-2 text-xs">
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                          <Camera className="w-3.5 h-3.5" /> {exit.camera_id || 'Exit Camera'}
                        </div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
