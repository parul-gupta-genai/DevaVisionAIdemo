import React, { useEffect, useState } from 'react';
import { Users, UserCheck, UserX, Clock, Calendar, ChevronRight } from 'lucide-react';
import { cn } from '@/utils/utils';
import { api } from '@/api/api';
import { VisitorDetailModal } from '@/components/visitors/VisitorDetailModal';

export default function DashboardTab() {
  const [visitors, setVisitors] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedVisitor, setSelectedVisitor] = useState<any | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [visRes, evRes] = await Promise.all([
          api.get('/api/plugins/visitor').catch(() => ({ data: { data: [] } })),
          api.get('/api/plugins/visitor/events/all').catch(() => ({ data: [] }))
        ]);
        setVisitors(visRes.data?.data || []);
        setEvents(Array.isArray(evRes.data) ? evRes.data : []);
      } catch (err) {
        console.error("Failed to load visitors", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const activeVisitors = visitors.filter(v => v.status === 'ACTIVE' || v.status === 'ON_SITE');
  const departures = events.filter(e => e.event_type === 'EXIT' || e.event_type === 'DEPARTURE');
  const upcoming = visitors.filter(v => v.status === 'EXPECTED' || v.status === 'PENDING' || v.status === 'REGISTERED');

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon={Users} label="Registered / Expected" value={upcoming.length.toString()} tone="bg-blue-500/20 text-blue-400 border-blue-500/30" />
        <Stat icon={UserCheck} label="Active Visitors" value={activeVisitors.length.toString()} tone="bg-emerald-500/20 text-emerald-400 border-emerald-500/30" />
        <Stat icon={Clock} label="Total Enrolled" value={visitors.length.toString()} tone="bg-indigo-500/20 text-indigo-400 border-indigo-500/30" />
        <Stat icon={UserX} label="Violations" value="0" tone="bg-danger/20 text-danger border-danger/30" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass border border-foreground/10 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-foreground dark:text-white">Registered & Upcoming Visitors</h3>
            <span className="text-xs text-muted-foreground">Click card for details</span>
          </div>

          {upcoming.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground text-sm flex flex-col items-center justify-center gap-2">
              <Calendar className="w-8 h-8 opacity-40" />
              <span>No registered visitors yet.</span>
            </div>
          ) : (
            <div className="space-y-3">
              {upcoming.map((v, i) => (
                <div 
                  key={v.visitor_id || i} 
                  onClick={() => setSelectedVisitor(v)}
                  className="flex items-center justify-between p-3.5 rounded-xl bg-background/40 border border-foreground/5 hover:border-primary/40 hover:bg-foreground/5 transition-all cursor-pointer group shadow-sm"
                >
                  <div className="flex items-center gap-3">
                    {v.photo ? (
                      <img 
                        src={`/${v.photo}`} 
                        alt={v.name} 
                        className="w-11 h-11 rounded-full object-cover border-2 border-primary/40 group-hover:border-primary shadow-sm transition-all" 
                        onError={(e) => {
                          (e.target as HTMLElement).style.display = 'none';
                        }}
                      />
                    ) : (
                      <div className="w-11 h-11 rounded-full bg-foreground/10 flex items-center justify-center font-bold text-foreground dark:text-white group-hover:bg-primary/20 group-hover:text-primary transition-all">
                        {v.name ? v.name.slice(0, 2).toUpperCase() : `V${i+1}`}
                      </div>
                    )}
                    <div>
                      <div className="font-bold text-foreground dark:text-white text-sm flex items-center gap-2">
                        {v.name || `Visitor ${i+1}`}
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-foreground/10 text-primary border border-primary/20">{v.visitor_id}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">{v.role || 'Guest'} {v.email ? `• ${v.email}` : ''}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className="text-xs font-mono text-foreground dark:text-white">
                        {v.created_at ? new Date(v.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Today'}
                      </div>
                      <div className="text-[10px] uppercase font-bold text-emerald-400">
                        {v.status || 'Registered'}
                      </div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="glass border border-foreground/10 rounded-2xl p-6">
          <h3 className="text-lg font-bold text-foreground dark:text-white mb-4">Recent Departures</h3>
          {departures.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground text-sm flex flex-col items-center justify-center gap-2">
              <Clock className="w-8 h-8 opacity-40" />
              <span>No recent departures recorded.</span>
            </div>
          ) : (
            <div className="space-y-3">
              {departures.map((d, i) => (
                <div key={d.event_id || i} className="flex items-center justify-between p-3 rounded-xl bg-background/40 border border-foreground/5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-foreground/10 flex items-center justify-center font-bold text-foreground dark:text-white">
                      {d.visitor_name ? d.visitor_name.slice(0, 2).toUpperCase() : `V${i+1}`}
                    </div>
                    <div>
                      <div className="font-bold text-foreground dark:text-white text-sm">{d.visitor_name || `Visitor`}</div>
                      <div className="text-xs text-muted-foreground">{d.timestamp ? new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] uppercase font-bold text-muted-foreground">Left</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Visitor Detail Modal */}
      {selectedVisitor && (
        <VisitorDetailModal
          visitorId={selectedVisitor.visitor_id}
          initialVisitor={selectedVisitor}
          onClose={() => setSelectedVisitor(null)}
        />
      )}
    </div>
  );
}

function Stat({ icon: Icon, label, value, tone }: any) {
  return (
    <div className={cn("glass border rounded-xl p-5 flex items-center gap-4", tone)}>
      <div className={cn('p-3 rounded-xl bg-background/40 shadow-sm', tone)}>
        <Icon className="w-6 h-6" />
      </div>
      <div>
        <div className="text-[10px] uppercase font-bold tracking-widest opacity-80 mb-1">{label}</div>
        <div className="text-3xl font-black leading-tight text-foreground dark:text-white">{value}</div>
      </div>
    </div>
  );
}
