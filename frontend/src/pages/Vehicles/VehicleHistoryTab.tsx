import React, { useState } from 'react';
import { Download, Search } from 'lucide-react';

export default function VehicleHistoryTab() {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const [search, setSearch] = useState('');

  const history = [
    { id: 1, plate: "HR26 DQ 5551", type: "Employee", date: "2026-09-05", in: "08:30 AM", out: "06:15 PM", duration: "9h 45m", inCamera: "Gate 1 Entry", outCamera: "Gate 2 Exit" },
    { id: 2, plate: "DL9C AB 1234", type: "Visitor", date: "2026-09-05", in: "11:00 AM", out: "01:30 PM", duration: "2h 30m", inCamera: "Gate 1 Entry", outCamera: "Gate 1 Exit" },
    { id: 3, plate: "UP16 TZ 9999", type: "Contractor", date: "2026-09-05", in: "07:15 AM", out: "05:00 PM", duration: "9h 45m", inCamera: "Service Gate", outCamera: "Service Gate" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide">Vehicle History</h2>
          <p className="text-sm text-muted-foreground">Log of all vehicle movements in the premises.</p>
        </div>
        <div className="flex gap-2">
          <input type="date" value={day} max={new Date().toISOString().slice(0, 10)} onChange={e => setDay(e.target.value)} className="bg-background/60 border border-foreground/10 rounded-lg px-3 py-2 text-sm text-white outline-none" />
          <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-foreground/10 text-white text-sm font-medium hover:bg-foreground/20 transition-colors"><Download className="w-4 h-4"/> Export CSV</button>
        </div>
      </div>

      <div className="glass border border-foreground/10 rounded-2xl overflow-hidden">
        <div className="p-4 flex items-center gap-3 border-b border-foreground/10 bg-background/20">
          <Search className="w-5 h-5 text-muted-foreground" />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by license plate or type..."
            className="bg-transparent outline-none text-sm text-white flex-1"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-[10px] tracking-wider uppercase text-muted-foreground bg-foreground/5 font-black">
              <tr>
                <th className="px-6 py-4">License Plate</th>
                <th className="px-6 py-4">Type</th>
                <th className="px-6 py-4">Entry</th>
                <th className="px-6 py-4">Exit</th>
                <th className="px-6 py-4">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {history.map(r => (
                <tr key={r.id} className="hover:bg-foreground/5 transition-colors">
                  <td className="px-6 py-4">
                    <div className="font-bold text-white font-mono bg-background/50 px-2 py-1 rounded inline-block border border-foreground/5">{r.plate}</div>
                  </td>
                  <td className="px-6 py-4 text-muted-foreground font-medium">{r.type}</td>
                  <td className="px-6 py-4">
                    <div className="text-success font-mono text-xs font-bold mb-1">{r.in}</div>
                    <div className="text-[10px] text-muted-foreground">{r.inCamera}</div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-warning font-mono text-xs font-bold mb-1">{r.out}</div>
                    <div className="text-[10px] text-muted-foreground">{r.outCamera}</div>
                  </td>
                  <td className="px-6 py-4 text-white font-mono font-bold">{r.duration}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
