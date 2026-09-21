import React, { useEffect, useState } from 'react';
import { Download, Search, Package } from 'lucide-react';
import { cn } from '@/utils/utils';
import { api } from '@/api/api';

interface MaterialEvent {
  id: string;
  material_type: string;
  event_type: 'In' | 'Out' | string;
  quantity: number;
  timestamp: string;
  camera_name?: string;
  camera_id?: string;
}

export default function HistoryTab() {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const [search, setSearch] = useState('');
  const [events, setEvents] = useState<MaterialEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHistory = async () => {
      setLoading(true);
      try {
        const res = await api.get('/api/plugins/material/events', {
          params: { date: day, limit: 200 },
        });
        const items = res.data ?? [];
        setEvents(Array.isArray(items) ? items : []);
      } catch {
        setEvents([]);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, [day]);

  const filtered = events.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      r.material_type?.toLowerCase().includes(q) ||
      r.camera_name?.toLowerCase().includes(q)
    );
  });

  const handleExport = () => {
    if (filtered.length === 0) return;
    const header = 'Material,Type,Quantity,Time,Camera\n';
    const rows = filtered.map(r => {
      const time = new Date(r.timestamp).toLocaleTimeString();
      return `"${r.material_type}","${r.event_type}","${r.quantity}","${time}","${r.camera_name ?? r.camera_id ?? ''}"`;
    });
    const blob = new Blob([header + rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `material-history-${day}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide">Material History</h2>
          <p className="text-sm text-muted-foreground">Log of all material movements (In/Out).</p>
        </div>
        <div className="flex gap-2">
          <input
            type="date"
            value={day}
            max={new Date().toISOString().slice(0, 10)}
            onChange={e => setDay(e.target.value)}
            className="bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white outline-none"
          />
          <button
            onClick={handleExport}
            disabled={filtered.length === 0}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-foreground/10 text-white text-sm font-medium hover:bg-foreground/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
        </div>
      </div>

      <div className="glass border border-foreground/10 rounded-2xl overflow-hidden">
        <div className="p-4 flex items-center gap-3 border-b border-foreground/10 bg-background/20">
          <Search className="w-5 h-5 text-muted-foreground" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search material type or camera..."
            className="bg-transparent outline-none text-sm text-white flex-1"
          />
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-foreground/40 text-center">
            <Package className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm font-medium">No material events for this date</p>
            <p className="text-xs mt-1">Events will appear here once cameras with the Material plugin detect movements.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-[10px] tracking-wider uppercase text-muted-foreground bg-foreground/5 font-black">
                <tr>
                  <th className="px-6 py-4">Material</th>
                  <th className="px-6 py-4">Type</th>
                  <th className="px-6 py-4">Quantity</th>
                  <th className="px-6 py-4">Time</th>
                  <th className="px-6 py-4">Camera</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filtered.map(r => (
                  <tr key={r.id} className="hover:bg-foreground/5 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-bold text-white">{r.material_type}</div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={cn(
                        'px-2 py-1 rounded text-xs font-bold uppercase',
                        r.event_type === 'In' ? 'bg-success/20 text-success' : 'bg-indigo-500/20 text-indigo-400'
                      )}>
                        {r.event_type}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="font-mono text-white font-bold">{r.quantity}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-white text-xs">
                        {new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-muted-foreground text-xs">
                      {r.camera_name ?? r.camera_id ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
