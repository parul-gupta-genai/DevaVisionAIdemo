import React, { useEffect, useState } from 'react';
import { EyeOff, AlertOctagon, UserPlus, ShieldCheck } from 'lucide-react';
import { cn } from '@/utils/utils';
import { api } from '@/api/api';

export default function WatchlistTab() {
  const [watchlist, setWatchlist] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);

  const fetchWatchlist = async () => {
    try {
      const res = await api.get('/api/face/watchlist').catch(() => ({ data: [] }));
      const items = Array.isArray(res.data) ? res.data : (res.data?.entries || []);
      setWatchlist(items);
    } catch (err) {
      console.error("Failed to load watchlist", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWatchlist();
  }, []);

  const handleRemove = async (entryId: string) => {
    try {
      await api.delete(`/api/face/watchlist/${entryId}`);
      fetchWatchlist();
    } catch (err) {
      alert("Failed to remove entry from watchlist");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide">Visitor Watchlist</h2>
          <p className="text-sm text-muted-foreground">Manage banned or flagged individuals.</p>
        </div>
        <button 
          onClick={() => setAddOpen(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-danger text-white text-sm font-bold shadow-lg shadow-danger/20 hover:bg-danger/80 transition-colors cursor-pointer"
        >
          <UserPlus className="w-4 h-4"/> Add to Watchlist
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {watchlist.length === 0 ? (
          <div className="lg:col-span-3 p-12 text-center text-muted-foreground text-sm glass rounded-2xl border border-foreground/5 flex flex-col items-center justify-center gap-3">
            <ShieldCheck className="w-12 h-12 text-emerald-500/50" />
            <span className="text-white font-medium">Watchlist is Clear</span>
            <span className="text-xs">No individuals are currently flagged on the security watchlist.</span>
          </div>
        ) : (
          watchlist.map(person => (
            <div key={person.entry_id || person.id} className="glass border border-foreground/10 rounded-2xl overflow-hidden shadow-lg flex flex-col">
              <div className={cn("p-4 border-b flex items-center justify-between", 
                person.severity === 'critical' ? 'bg-danger/10 border-danger/20' : 'bg-warning/10 border-warning/20'
              )}>
                <div className="flex items-center gap-2">
                  <AlertOctagon className={cn("w-5 h-5", person.severity === 'critical' ? 'text-danger' : 'text-warning')} />
                  <span className={cn("text-xs font-black uppercase tracking-widest", person.severity === 'critical' ? 'text-danger' : 'text-warning')}>
                    {person.severity || 'High'} Risk
                  </span>
                </div>
                <EyeOff className="w-4 h-4 text-muted-foreground" />
              </div>
              <div className="p-6 flex-1 flex flex-col">
                <div className="w-16 h-16 rounded-full bg-background/50 border border-foreground/10 mb-4 self-center flex items-center justify-center overflow-hidden">
                  {person.photo ? (
                    <img src={person.photo} alt={person.person_name} className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-xs text-muted-foreground font-semibold">Photo</span>
                  )}
                </div>
                <h3 className="text-lg font-black text-white text-center mb-1">{person.person_name || person.name}</h3>
                <p className="text-xs text-center text-muted-foreground mb-4">Category: {person.category || 'General'}</p>
                
                <div className="bg-background/40 rounded-xl p-3 border border-foreground/5 mt-auto">
                  <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-1">Reason</div>
                  <div className="text-sm text-white">{person.reason || 'Flagged for security review'}</div>
                </div>
              </div>
              <div className="p-4 border-t border-foreground/10 flex justify-end bg-background/20">
                <button 
                  onClick={() => handleRemove(person.entry_id)}
                  className="text-xs font-bold text-danger hover:text-danger/80 transition-colors"
                >
                  Remove
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {addOpen && (
        <AddWatchlistModal 
          onClose={() => setAddOpen(false)} 
          onSuccess={() => { setAddOpen(false); fetchWatchlist(); }} 
        />
      )}
    </div>
  );
}

function AddWatchlistModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [query, setQuery] = useState('');
  const [people, setPeople] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [category, setCategory] = useState('BLACKLIST');
  const [severity, setSeverity] = useState('critical');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const resolvePhotoUrl = (p?: string | null) => {
    if (!p) return null;
    if (p.startsWith('http://') || p.startsWith('https://') || p.startsWith('data:')) return p;
    return p.startsWith('/') ? p : `/${p}`;
  };

  useEffect(() => {
    const fetchPersons = async () => {
      try {
        const res = await api.get('/api/face/persons', { params: { search: query || undefined, limit: 20 } });
        const items = res.data?.items || [];
        setPeople(items);
        if (items.length > 0 && !selected) {
          setSelected(items[0]);
        }
      } catch (err) {}
    };
    fetchPersons();
  }, [query]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) {
      setError("Please select an enrolled person from the list.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.post('/api/face/watchlist', {
        person_id: selected.person_id,
        category,
        severity,
        reason: reason || 'Flagged via Visitor Watchlist'
      });
      onSuccess();
    } catch (err: any) {
      const msg = err?.response?.data?.detail?.message || err?.response?.data?.detail || 'Failed to add person to watchlist.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 flex items-center justify-center p-4 backdrop-blur-xs" onClick={onClose}>
      <div className="bg-white border border-slate-200 shadow-2xl rounded-2xl p-6 w-full max-w-lg space-y-4 text-slate-900" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <AlertOctagon className="w-5 h-5 text-danger" /> Add Person to Watchlist
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-sm font-bold cursor-pointer">✕</button>
        </div>

        {error && (
          <div className="p-3 bg-danger/10 border border-danger/20 text-danger text-xs rounded-xl">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider block mb-1.5">Search Enrolled Person</label>
            <input 
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search by name or ID..." 
              className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-primary/40 focus:border-primary outline-none"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider block mb-1.5">Select Candidate ({people.length})</label>
            {people.length > 0 ? (
              <div className="max-h-40 overflow-y-auto rounded-xl border border-slate-200 divide-y divide-slate-100 bg-slate-50/50">
                {people.map(p => {
                  const photoUrl = resolvePhotoUrl(p.photo);
                  const isSelected = selected?.person_id === p.person_id;
                  const initial = p.name ? p.name.trim().charAt(0).toUpperCase() : 'U';
                  return (
                    <div 
                      key={p.person_id}
                      onClick={() => { setSelected(p); }}
                      className={`p-2.5 text-xs flex justify-between items-center cursor-pointer transition-colors ${isSelected ? 'bg-blue-50 border-l-4 border-blue-600 font-bold' : 'hover:bg-slate-100'}`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-9 h-9 rounded-lg overflow-hidden shrink-0 border border-slate-200 bg-slate-100 flex items-center justify-center">
                          {photoUrl ? (
                            <img src={photoUrl} alt={p.name} className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                          ) : null}
                          <span className="font-bold text-xs text-slate-600">{initial}</span>
                        </div>
                        <div className="min-w-0">
                          <div className="text-slate-900 font-semibold truncate">{p.name}</div>
                          <div className="text-slate-500 font-mono text-[11px]">{p.person_code || p.person_id}</div>
                        </div>
                      </div>
                      {isSelected && <span className="text-[10px] bg-blue-600 text-white font-bold px-2 py-0.5 rounded shrink-0">Selected</span>}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-3 bg-slate-50 rounded-xl text-[11px] text-slate-500 border border-slate-200">
                No enrolled faces found. Enrol people in <a href="/employee-db" className="text-primary underline">Employee Directory</a> or <a href="/face-watchlist" className="text-primary underline">Face Watchlist</a>.
              </div>
            )}
          </div>

          {selected && (
            <div className="p-3 bg-blue-50/80 border border-blue-200 rounded-xl flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg overflow-hidden border-2 border-blue-500 bg-white flex items-center justify-center shrink-0">
                {resolvePhotoUrl(selected.photo) ? (
                  <img src={resolvePhotoUrl(selected.photo)!} alt={selected.name} className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                ) : null}
                <span className="font-bold text-sm text-blue-600">{selected.name?.charAt(0)?.toUpperCase() || 'U'}</span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-bold text-blue-700 uppercase tracking-wide">Target Person</div>
                <div className="text-sm font-bold text-slate-900 truncate">{selected.name}</div>
                <div className="text-xs text-slate-500 font-mono">{selected.person_code || selected.person_id}</div>
              </div>
              <span className="px-2 py-1 rounded bg-blue-600 text-white text-xs font-semibold shrink-0">
                Ready
              </span>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider block mb-1.5">Category</label>
              <select 
                value={category}
                onChange={e => setCategory(e.target.value)}
                className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3 py-2 text-sm text-slate-900 focus:ring-2 focus:ring-primary/40 focus:border-primary outline-none"
              >
                <option value="BLACKLIST">BLACKLIST</option>
                <option value="PERSON_OF_INTEREST">PERSON OF INTEREST</option>
                <option value="EX_EMPLOYEE">EX-EMPLOYEE</option>
                <option value="VIP">VIP</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider block mb-1.5">Severity</label>
              <select 
                value={severity}
                onChange={e => setSeverity(e.target.value)}
                className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3 py-2 text-sm text-slate-900 focus:ring-2 focus:ring-primary/40 focus:border-primary outline-none"
              >
                <option value="critical">Critical</option>
                <option value="warning">Warning</option>
                <option value="info">Info</option>
              </select>
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider block mb-1.5">Reason / Incident Description</label>
            <textarea 
              rows={2}
              value={reason}
              onChange={e => setReason(e.target.value)}
              placeholder="Enter reason for security flagging..."
              className="w-full bg-slate-50 border border-slate-300 rounded-xl p-3 text-sm text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-primary/40 focus:border-primary outline-none"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2 border-t border-slate-100">
            <button 
              type="button" 
              onClick={onClose} 
              className="px-4 py-2 rounded-xl text-sm font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button 
              type="submit" 
              disabled={busy}
              className="px-5 py-2 rounded-xl text-sm font-bold bg-danger hover:bg-danger/80 text-white transition-colors disabled:opacity-50 cursor-pointer shadow-sm shadow-danger/20"
            >
              {busy ? "Adding..." : "Add to Watchlist"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
