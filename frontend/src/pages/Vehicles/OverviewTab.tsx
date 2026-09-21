import React, { useEffect, useState } from 'react';
import { Car, LogIn, LogOut, AlertOctagon, ShieldAlert, CheckCircle2 } from 'lucide-react';
import { cn } from '@/utils/utils';
import { api } from '@/api/api';

interface VehicleStats {
  vehicles_inside: number;
  entries_today: number;
  exits_today: number;
  unauthorized: number;
  blacklist_matches: number;
  parking_occupancy_pct: number | null;
}

interface ANPREvent {
  id: string;
  plate_number: string;
  camera_name?: string;
  timestamp: string | number;
  event_type: string;
}

interface ParkingZone {
  camera_id: string;
  camera_name?: string;
  occupied_spots: number;
  total_spots: number;
}

export default function OverviewTab() {
  const [stats, setStats] = useState<VehicleStats | null>(null);
  const [recentANPR, setRecentANPR] = useState<ANPREvent[]>([]);
  const [parkingZones, setParkingZones] = useState<ParkingZone[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAll = async () => {
      try {
        // Fetch ANPR stats for top counts
        const [anprStatsRes, anprHistoryRes, parkingRes] = await Promise.allSettled([
          api.get('/api/plugins/anpr/stats'),
          api.get('/api/plugins/anpr/search?limit=3'),
          api.get('/api/parking/stats'),
        ]);

        // ANPR stats → top metric cards
        if (anprStatsRes.status === 'fulfilled') {
          const d = anprStatsRes.value.data;
          setStats({
            vehicles_inside: d?.vehicles_inside ?? 0,
            entries_today: d?.entries_today ?? 0,
            exits_today: d?.exits_today ?? 0,
            unauthorized: d?.unauthorized ?? 0,
            blacklist_matches: d?.blacklist_matches ?? 0,
            parking_occupancy_pct: d?.parking_occupancy_pct ?? null,
          });
        } else {
          // API failed or not available — show zeros
          setStats({
            vehicles_inside: 0,
            entries_today: 0,
            exits_today: 0,
            unauthorized: 0,
            blacklist_matches: 0,
            parking_occupancy_pct: null,
          });
        }

        // Recent ANPR detections
        if (anprHistoryRes.status === 'fulfilled') {
          const items = anprHistoryRes.value.data ?? [];
          setRecentANPR(Array.isArray(items) ? items : []);
        }

        // Parking zones
        if (parkingRes.status === 'fulfilled') {
          const current = parkingRes.value.data?.current ?? {};
          const zones: ParkingZone[] = Object.entries(current).map(([cam_id, data]: [string, any]) => ({
            camera_id: cam_id,
            camera_name: data.camera_name,
            occupied_spots: data.occupied_spots ?? 0,
            total_spots: data.total_spots ?? 0,
          }));
          setParkingZones(zones);
        }
      } catch (err) {
        console.error('Vehicle overview fetch failed', err);
      } finally {
        setLoading(false);
      }
    };

    fetchAll();
    const interval = setInterval(fetchAll, 15000);
    return () => clearInterval(interval);
  }, []);

  const parkingOccupancyDisplay =
    stats?.parking_occupancy_pct != null
      ? `${Math.round(stats.parking_occupancy_pct)}%`
      : '—';

  return (
    <div className="space-y-6">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <Stat icon={Car} label="Vehicles Inside" value={loading ? '—' : String(stats?.vehicles_inside ?? 0)} tone="bg-blue-500/20 text-blue-400 border-blue-500/30" />
        <Stat icon={LogIn} label="Entries Today" value={loading ? '—' : String(stats?.entries_today ?? 0)} tone="bg-emerald-500/20 text-emerald-400 border-emerald-500/30" />
        <Stat icon={LogOut} label="Exits Today" value={loading ? '—' : String(stats?.exits_today ?? 0)} tone="bg-indigo-500/20 text-indigo-400 border-indigo-500/30" />
        <Stat icon={ShieldAlert} label="Unauthorized" value={loading ? '—' : String(stats?.unauthorized ?? 0)} tone="bg-orange-500/20 text-orange-400 border-orange-500/30" />
        <Stat icon={AlertOctagon} label="Blacklist Matches" value={loading ? '—' : String(stats?.blacklist_matches ?? 0)} tone="bg-danger/20 text-danger border-danger/30" />
        <Stat icon={CheckCircle2} label="Parking Occupancy" value={loading ? '—' : parkingOccupancyDisplay} tone="bg-purple-500/20 text-purple-400 border-purple-500/30" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent ANPR Detections */}
        <div className="glass border border-foreground/10 rounded-2xl p-6">
          <h3 className="text-lg font-bold text-white mb-4">Recent ANPR Detections</h3>
          {recentANPR.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-center text-foreground/40">
              <Car className="w-10 h-10 mb-3 opacity-30" />
              <p className="text-sm font-medium">No detections yet</p>
              <p className="text-xs mt-1">ANPR events will appear here once cameras are active.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {recentANPR.map((evt) => {
                const mins = evt.timestamp
                  ? Math.max(0, Math.round((Date.now() - new Date(evt.timestamp).getTime()) / 60000))
                  : null;
                return (
                  <div key={evt.id} className="flex items-center justify-between p-3 rounded-xl bg-background/40 border border-foreground/5">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-10 rounded-lg bg-foreground/10 flex items-center justify-center">
                        <Car className="w-5 h-5 text-muted-foreground" />
                      </div>
                      <div>
                        <div className="font-bold font-mono bg-warning/20 text-warning px-2 py-0.5 rounded text-sm inline-block">
                          {evt.plate_number}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {evt.camera_name ?? 'Camera'} • {mins !== null ? `${mins} min ago` : '—'}
                        </div>
                      </div>
                    </div>
                    <div className="text-[10px] uppercase font-bold text-success">Verified</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Parking Zones */}
        <div className="glass border border-foreground/10 rounded-2xl p-6">
          <h3 className="text-lg font-bold text-white mb-4">Parking Zones</h3>
          {parkingZones.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-center text-foreground/40">
              <CheckCircle2 className="w-10 h-10 mb-3 opacity-30" />
              <p className="text-sm font-medium">No parking zones configured</p>
              <p className="text-xs mt-1">Add cameras with Parking plugin to see zone data.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {parkingZones.map((zone) => {
                const pct = zone.total_spots > 0 ? zone.occupied_spots / zone.total_spots : 0;
                const isNearFull = pct > 0.8;
                return (
                  <div key={zone.camera_id} className="flex flex-col gap-2 p-4 rounded-xl bg-background/40 border border-foreground/5">
                    <div className="flex justify-between items-center">
                      <div className="font-bold text-white text-sm">{zone.camera_name ?? zone.camera_id}</div>
                      <div className={cn('text-[10px] uppercase font-bold', isNearFull ? 'text-warning' : 'text-success')}>
                        {isNearFull ? 'Near Full' : 'Normal'}
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="flex-1 h-2 bg-background/40 rounded-full overflow-hidden">
                        <div
                          className={cn('h-full', isNearFull ? 'bg-warning' : 'bg-primary')}
                          style={{ width: `${pct * 100}%` }}
                        />
                      </div>
                      <div className="text-xs font-mono text-muted-foreground font-bold">
                        {zone.occupied_spots} / {zone.total_spots}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ icon: Icon, label, value, tone }: { icon: any; label: string; value: string; tone: string }) {
  return (
    <div className={cn('glass border rounded-xl p-5 flex flex-col gap-3', tone)}>
      <div className={cn('p-2 rounded-lg bg-background/40 w-fit', tone)}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <div className="text-2xl font-black leading-tight text-white mb-1">{value}</div>
        <div className="text-[10px] uppercase font-bold tracking-widest opacity-80">{label}</div>
      </div>
    </div>
  );
}
