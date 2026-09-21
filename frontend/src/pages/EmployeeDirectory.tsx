import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '@/api/api';
import { QRCodeSVG } from 'qrcode.react';
import { QrCode, X, Filter, Trash2, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface VisitorProfile {
  visitor_id: string;
  name: string;
  email?: string;
  photo?: string;
  first_seen?: string;
  last_seen?: string;
  total_visits: number;
  status: string;
  created_at: string;
}

export default function EmployeeDirectory() {
  const [profiles, setProfiles] = useState<VisitorProfile[]>([]);
  const [showQrModal, setShowQrModal] = useState<boolean>(false);
  const currentRole = 'EMPLOYEE';
  const [safeUrl, setSafeUrl] = useState((import.meta.env.VITE_PUBLIC_URL || window.location.origin).replace(/\/+$/, ''));

  useEffect(() => {
    const fetchIp = async () => {
      try {
        const res = await api.get('/api/system/ip');
        if (res.data && res.data.ip) {
          const port = window.location.port ? `:${window.location.port}` : '';
          const protocol = window.location.protocol;
          // Only replace if currently on localhost/127.0.0.1 AND no public URL is configured
          if (!import.meta.env.VITE_PUBLIC_URL && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
            setSafeUrl(`${protocol}//${res.data.ip}${port}`);
          }
        }
      } catch (e) {
        console.error("Failed to fetch system IP", e);
      }
    };
    fetchIp();
  }, []);
  
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  
  // Pagination State
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const limit = 50;
  
  const fetchProfiles = useCallback(async (currentPage: number = page, role: string = currentRole) => {
    try {
      const res = await api.get(`/api/plugins/visitor?page=${currentPage}&limit=${limit}&role=${role}`);
      setProfiles(res.data.data);
      setTotal(res.data.total);
    } catch (error) {
      console.error("Failed to fetch profiles", error);
    }
  }, [page, limit]);
  
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Fetch initial data
    fetchProfiles(1, currentRole);

    // Connect WebSocket to listen for new registrations in real-time
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = localStorage.getItem('access_token') || '';
    ws.current = new WebSocket(`${protocol}//${window.location.host}/ws/events?token=${encodeURIComponent(token)}`);
    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      let shouldRefresh = false;
      Object.values(data).forEach((camData: any) => {
        if (camData.events && camData.events.VisitorPlugin) {
          camData.events.VisitorPlugin.forEach((ev: any) => {
            if (ev.event_type === 'EMPLOYEE_REGISTERED') {
              shouldRefresh = true;
            }
          });
        }
      });
      if (shouldRefresh) {
        // Fetch fresh profiles list to ensure we have the photo and correct DB fields
        fetchProfiles(page, currentRole);
      }
    };
    return () => ws.current?.close();
  }, [fetchProfiles, page, currentRole]);



  const filteredProfiles = profiles.filter(p => {
    if (!startDate && !endDate) return true;
    const dateStr = p.created_at.endsWith('Z') ? p.created_at : p.created_at + 'Z';
    const pDate = new Date(dateStr);
    if (startDate && pDate < new Date(startDate)) return false;
    if (endDate) {
      const end = new Date(endDate);
      end.setHours(23, 59, 59, 999);
      if (pDate > end) return false;
    }
    return true;
  });

  const handleBulkDelete = async () => {
    if (!startDate || !endDate) {
      alert("Please select both a Start Date and End Date to perform a bulk delete.");
      return;
    }
    
    if (confirm(`Are you absolutely sure you want to permanently delete ${filteredProfiles.length} visitor(s) registered between ${startDate} and ${endDate}?\nThis action cannot be undone and will delete their historical entry logs as well.`)) {
      setIsDeleting(true);
      try {
        const end = new Date(endDate);
        end.setHours(23, 59, 59, 999);
        
        await api.delete('/api/plugins/visitor/bulk', {
          data: {
            start_time: new Date(startDate).toISOString(),
            end_time: end.toISOString()
          }
        });
        
        // Refresh
        await fetchProfiles();
      } catch (e) {
        alert("Failed to delete visitors.");
      } finally {
        setIsDeleting(false);
      }
    }
  };

  return (
    <div className="p-6 min-h-screen text-white relative z-10">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <h1 className="text-3xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent drop-shadow-sm">
          Employee Management
        </h1>
      </div>
      
      <div className="glass-pro p-6 rounded-2xl">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
          <h2 className="text-xl font-semibold text-primary">Registered Employees</h2>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 bg-background/40 p-1.5 rounded-lg border border-foreground/5 backdrop-blur-md">
              <Filter className="w-4 h-4 text-gray-400 ml-1" />
              <input 
                type="date" 
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="bg-transparent border-none text-sm text-gray-300 focus:outline-none focus:ring-0 w-32"
              />
              <span className="text-gray-500">to</span>
              <input 
                type="date" 
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="bg-transparent border-none text-sm text-gray-300 focus:outline-none focus:ring-0 w-32"
              />
            </div>
            
            {startDate && endDate && (
              <button 
                onClick={handleBulkDelete}
                disabled={isDeleting || filteredProfiles.length === 0}
                className="bg-red-900/30 hover:bg-red-600 border border-red-800 hover:border-red-500 text-red-300 hover:text-white px-4 py-2 rounded-lg text-sm font-medium transition flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Trash2 className="w-4 h-4" /> {isDeleting ? 'Deleting...' : `Delete Range (${filteredProfiles.length})`}
              </button>
            )}
            
            <div className="flex gap-2">
              <button 
                onClick={() => setShowQrModal(true)}
                className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-teal-500 to-emerald-600 text-white rounded-lg hover:from-teal-400 hover:to-emerald-500 transition-all font-medium shadow-[0_0_20px_rgba(20,184,166,0.3)] hover:shadow-[0_0_30px_rgba(20,184,166,0.5)] border border-foreground/10"
              >
                <QrCode className="w-4 h-4" />
                Generate Employee QR
              </button>
            </div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400 text-sm">
                <th className="pb-3 pl-2 font-medium">Profile</th>
                <th className="pb-3 font-medium">Email</th>
                <th className="pb-3 font-medium">ID</th>
                <th className="pb-3 font-medium text-right pr-2">Registration Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              <AnimatePresence>
              {filteredProfiles.map((p, i) => (
                <motion.tr 
                  key={p.visitor_id || i} 
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.2, delay: Math.min(i * 0.05, 0.5) }}
                  className="hover:bg-primary/10 transition-colors group"
                >
                  <td className="py-3 pl-2">
                    <div className="flex items-center gap-3">
                      {p.photo ? (
                        <img src={`/${p.photo}`} alt={p.name} className="w-10 h-10 rounded-full object-cover border border-primary/30 group-hover:border-primary transition-colors shadow-sm" />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center font-bold text-lg text-secondary-foreground border border-border group-hover:border-primary transition-colors">
                          {p.name.charAt(0)}
                        </div>
                      )}
                      <span className="font-medium text-foreground group-hover:text-primary transition-colors">{p.name}</span>
                    </div>
                  </td>
                  <td className="py-3 text-muted-foreground text-sm">
                    {p.email || <span className="text-gray-600 italic">Not provided</span>}
                  </td>
                  <td className="py-3">
                    <span className="font-mono text-xs bg-gray-800/80 text-gray-300 px-2 py-1 rounded border border-gray-700">
                      {p.visitor_id}
                    </span>
                  </td>
                  <td className="py-3 text-right pr-2">
                    <div className="text-sm text-gray-300 flex flex-col items-end">
                      <span className="font-medium">{new Date(p.created_at.endsWith('Z') ? p.created_at : p.created_at + 'Z').toLocaleDateString()}</span>
                      <span className="text-xs text-indigo-400/80 font-mono mt-0.5">
                        {new Date(p.created_at.endsWith('Z') ? p.created_at : p.created_at + 'Z').toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                    </div>
                  </td>
                </motion.tr>
              ))}
              </AnimatePresence>
              {filteredProfiles.length === 0 && (
                <motion.tr initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <td colSpan={4} className="py-12 text-center text-muted-foreground text-sm">
                    No employees found matching your filter criteria.
                  </td>
                </motion.tr>
              )}
            </tbody>
          </table>
        </div>
        
        {/* Pagination Controls */}
        {total > limit && (
          <div className="flex items-center justify-between border-t border-gray-800 pt-4 mt-4">
            <span className="text-sm text-gray-500">
              Showing {((page - 1) * limit) + 1} to {Math.min(page * limit, total)} of {total} employees
            </span>
            <div className="flex items-center gap-2">
              <button 
                onClick={() => {
                  const newPage = Math.max(1, page - 1);
                  setPage(newPage);
                  fetchProfiles(newPage);
                }}
                disabled={page === 1}
                className="p-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed border border-gray-700 transition"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <span className="text-sm font-medium px-2">Page {page} of {Math.ceil(total / limit)}</span>
              <button 
                onClick={() => {
                  const maxPage = Math.ceil(total / limit);
                  const newPage = Math.min(maxPage, page + 1);
                  setPage(newPage);
                  fetchProfiles(newPage);
                }}
                disabled={page >= Math.ceil(total / limit)}
                className="p-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed border border-gray-700 transition"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        )}
      </div>
      
      {showQrModal && (
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-background/60 backdrop-blur-md z-50 flex items-center justify-center p-4"
        >
          <motion.div 
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="glass-pro rounded-2xl w-full max-w-md overflow-hidden glow-primary"
          >
            <div className="p-4 border-b border-foreground/10 flex justify-between items-center bg-background/40">
              <h3 className="font-semibold text-lg text-white flex items-center gap-2"><QrCode className="w-5 h-5 text-primary" /> Employee Registration QR</h3>
              <button onClick={() => setShowQrModal(false)} className="text-muted-foreground hover:text-white transition bg-foreground/5 hover:bg-foreground/10 p-1.5 rounded-full">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-8 flex flex-col items-center">
              <div className="bg-white p-5 rounded-2xl mb-6 shadow-2xl shadow-cyan-600/20 ring-4 ring-cyan-600/20">
                <QRCodeSVG value={`${safeUrl}/register?role=employee`} size={220} />
              </div>
              <p className="text-gray-300 text-center mb-6 text-sm font-medium">
                Scan this QR code to access the Self-Registration portal for Employees.
              </p>
              <div className="w-full mt-2">
                <label className="block text-[10px] font-bold text-primary mb-2 uppercase tracking-widest">Direct Registration Link</label>
                <div className="flex bg-background/50 border border-foreground/10 rounded-lg overflow-hidden focus-within:border-primary transition-colors">
                  <input 
                    type="text" 
                    readOnly 
                    value={`${safeUrl}/register?role=employee`}
                    className="w-full bg-transparent border-none text-xs text-gray-300 font-mono focus:outline-none p-2"
                  />
                  <button 
                    onClick={() => {
                      navigator.clipboard.writeText(`${safeUrl}/register?role=employee`);
                    }}
                    className="bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 px-3 transition-colors flex items-center justify-center border-l border-foreground/10"
                  >
                    Copy
                  </button>
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  Print the QR code above or share this link with employees.
                </p>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}
