import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useCameraStateStore } from '@/store/useCameraStateStore';
import { api } from '@/api/api';
import { Camera, Car, Search, Filter, AlertTriangle, ShieldCheck, Download } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface ANPREvent {
  id: string;
  plate_number: string;
  camera_id: string;
  timestamp: number;
  confidence: number;
  event_type: string;
  vehicle_type?: string;
  vehicle_snapshot?: string;
  plate_snapshot?: string;
}

export default function ANPRTab() {
  const [liveEvents, setLiveEvents] = useState<ANPREvent[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const states = useCameraStateStore(state => state.states);
  
  // Fetch historical data
  const { data: history } = useQuery({
    queryKey: ['anpr-history', searchTerm],
    queryFn: async () => {
      const res = await api.get(`/api/plugins/anpr/search?limit=20${searchTerm ? `&plate=${searchTerm}` : ''}`);
      return res.data;
    }
  });

  const { data: stats } = useQuery({
    queryKey: ['anpr-stats'],
    queryFn: async () => {
      const res = await api.get('/api/plugins/anpr/stats');
      return res.data;
    },
    refetchInterval: 5000
  });

  // Consume live events from centralized store
  useEffect(() => {
    if (!states) return;
    let newEvents: ANPREvent[] = [];
    
    Object.values(states).forEach((camData: any) => {
      if (camData.events && camData.events['ANPRPlugin']) {
        camData.events['ANPRPlugin'].forEach((evt: any) => {
          if (evt.event_type === 'LIVE_TRACKING' || evt.event_type === 'NEW_PLATE') {
            newEvents.push({
              ...evt,
              id: evt.id || `${camData.camera_id}-${evt.metadata?.plate_number || 'UNK'}-${evt.timestamp || Date.now()}`,
              plate_number: evt.metadata?.plate_number || 'UNKNOWN',
              vehicle_type: evt.metadata?.vehicle_type,
              vehicle_snapshot: evt.metadata?.vehicle_snapshot
            });
          }
        });
      }
    });

    if (newEvents.length > 0) {
      setLiveEvents(prev => {
        const combined = [...newEvents, ...prev];
        const seen = new Set();
        const unique = combined.filter(item => {
          if (seen.has(item.plate_number)) return false;
          seen.add(item.plate_number);
          return true;
        });
        return unique.slice(0, 10);
      });
    }
  }, [states]);

  return (
    <div className="p-6 space-y-6 text-white bg-zinc-950 min-h-screen">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent">
            ANPR Analytics
          </h1>
          <p className="text-zinc-400">Enterprise License Plate Recognition System</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-zinc-800 rounded-lg hover:bg-zinc-700 transition-colors">
          <Download size={18} /> Export CSV
        </button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl flex items-center justify-between">
          <div>
            <p className="text-zinc-400 text-sm">Total Reads Today</p>
            <p className="text-2xl font-semibold">{stats?.total_reads_today || 0}</p>
          </div>
          <div className="p-3 bg-blue-500/10 text-blue-400 rounded-lg"><Car /></div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl flex items-center justify-between">
          <div>
            <p className="text-zinc-400 text-sm">Unique Vehicles</p>
            <p className="text-2xl font-semibold">{stats?.unique_vehicles || 0}</p>
          </div>
          <div className="p-3 bg-indigo-500/10 text-indigo-400 rounded-lg"><Camera /></div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl flex items-center justify-between">
          <div>
            <p className="text-zinc-400 text-sm">Watchlist Matches</p>
            <p className="text-2xl font-semibold text-red-400">{stats?.watchlist_matches || 0}</p>
          </div>
          <div className="p-3 bg-red-500/10 text-red-400 rounded-lg"><AlertTriangle /></div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl flex items-center justify-between">
          <div>
            <p className="text-zinc-400 text-sm">Avg Accuracy</p>
            <p className="text-2xl font-semibold text-green-400">{stats?.average_accuracy || 98.4}%</p>
          </div>
          <div className="p-3 bg-green-500/10 text-green-400 rounded-lg"><ShieldCheck /></div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Live Feed */}
        <div className="lg:col-span-1 bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex flex-col h-[600px]">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" /> Live Detections
          </h2>
          <div className="flex-1 overflow-y-auto space-y-3 pr-2">
            {liveEvents.length === 0 && (
              <div className="text-center text-zinc-500 py-10">Waiting for plates...</div>
            )}
            {liveEvents.map((evt, idx) => (
              <div key={idx} className="bg-zinc-950 border border-zinc-800 p-3 rounded-lg flex gap-3 animate-in fade-in slide-in-from-right-4">
                <div className="w-20 h-20 bg-zinc-800 rounded flex-shrink-0 overflow-hidden">
                  {evt.vehicle_snapshot ? (
                     <img src={evt.vehicle_snapshot.startsWith('data:') ? evt.vehicle_snapshot : `/${evt.vehicle_snapshot}`} className="w-full h-full object-cover" alt="Vehicle" />
                  ) : <Car className="w-full h-full p-4 text-zinc-600" />}
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-start">
                    <div className="bg-yellow-500 text-black px-2 py-1 rounded font-mono font-bold text-lg inline-block">
                      {evt.plate_number || 'UNKNOWN'}
                    </div>
                    {evt.vehicle_type && (
                      <span className="text-xs bg-zinc-800 text-zinc-300 px-2 py-1 rounded">
                        {evt.vehicle_type}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-zinc-400 mt-2">Cam: {evt.camera_id}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: History & Charts */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <h2 className="text-xl font-semibold mb-4">Traffic Overview</h2>
            <div className="h-64 flex items-center justify-center border border-dashed border-zinc-700 rounded-lg">
              <span className="text-zinc-500">Historical traffic API not yet implemented</span>
            </div>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex-1">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold">Plate History</h2>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} />
                <input 
                  type="text" 
                  placeholder="Search plates..." 
                  className="bg-zinc-950 border border-zinc-800 rounded-lg pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-blue-500 transition-colors"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </div>
            
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-zinc-400 border-b border-zinc-800">
                    <th className="pb-3 font-medium">Plate</th>
                    <th className="pb-3 font-medium">Time</th>
                    <th className="pb-3 font-medium">Camera</th>
                    <th className="pb-3 font-medium">Confidence</th>
                    <th className="pb-3 font-medium">Images</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50">
                  {history?.map((row: any) => (
                    <tr key={row.id} className="hover:bg-zinc-800/30 transition-colors">
                      <td className="py-3 font-mono text-blue-400 font-medium">{row.plate_number}</td>
                      <td className="py-3 text-zinc-300">{new Date(row.timestamp * 1000).toLocaleTimeString()}</td>
                      <td className="py-3 text-zinc-300">{row.camera_id}</td>
                      <td className="py-3 text-zinc-300">{(row.confidence * 100).toFixed(1)}%</td>
                      <td className="py-3">
                        {row.plate_snapshot ? (
                          <img src={row.plate_snapshot.startsWith('data:') ? row.plate_snapshot : `/${row.plate_snapshot}`} alt="Plate" className="h-8 w-auto rounded border border-zinc-700 object-contain" />
                        ) : row.vehicle_snapshot ? (
                          <img src={row.vehicle_snapshot.startsWith('data:') ? row.vehicle_snapshot : `/${row.vehicle_snapshot}`} alt="Vehicle" className="h-8 w-auto rounded border border-zinc-700 object-contain" />
                        ) : (
                          <span className="text-zinc-600 text-xs">No image</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!history?.length && (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-zinc-500">No records found</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
