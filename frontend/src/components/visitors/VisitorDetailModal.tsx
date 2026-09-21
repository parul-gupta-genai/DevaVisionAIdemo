import React, { useEffect, useState } from 'react';
import { 
  X, User, Mail, Phone, ShieldCheck, Calendar, Clock, 
  Camera, QrCode, History, CheckCircle2, Sparkles, Send, Printer
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '@/api/api';

interface VisitorDetailModalProps {
  visitorId: string | null;
  initialVisitor?: any;
  onClose: () => void;
}

export const VisitorDetailModal: React.FC<VisitorDetailModalProps> = ({
  visitorId,
  initialVisitor,
  onClose
}) => {
  const [visitor, setVisitor] = useState<any>(initialVisitor || null);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(!initialVisitor);

  useEffect(() => {
    if (!visitorId) return;

    const fetchVisitorDetails = async () => {
      try {
        setLoading(true);
        const [vRes, hRes] = await Promise.all([
          api.get(`/api/plugins/visitor/${visitorId}`).catch(() => ({ data: initialVisitor })),
          api.get(`/api/plugins/visitor/${visitorId}/history`).catch(() => ({ data: [] }))
        ]);
        if (vRes.data) setVisitor(vRes.data);
        if (Array.isArray(hRes.data)) setHistory(hRes.data);
      } catch (err) {
        console.error("Failed to load visitor detail:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchVisitorDetails();
  }, [visitorId, initialVisitor]);

  if (!visitorId) return null;

  const currentVisitor = visitor || initialVisitor || {};

  const handleSendWhatsApp = () => {
    const phone = currentVisitor.phone || '';
    const cleanMobile = phone.replace(/\D/g, '');
    const mobileWithCountry = cleanMobile.length === 10 ? `91${cleanMobile}` : cleanMobile;
    const msg = encodeURIComponent(
      `Hello ${currentVisitor.name || 'Visitor'},\nYour Visitor Pass (#${currentVisitor.visitor_id}) at Hero Homes is confirmed.\nStatus: ${currentVisitor.status || 'Active'}\n\nDevaVision AI Security`
    );
    window.open(`https://wa.me/${mobileWithCountry || ''}?text=${msg}`, '_blank');
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
        {/* Backdrop click to close */}
        <div className="absolute inset-0" onClick={onClose} />

        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="relative z-10 w-full max-w-2xl bg-card border border-foreground/15 rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        >
          {/* Header */}
          <div className="relative bg-gradient-to-r from-blue-600/20 via-indigo-600/20 to-purple-600/20 border-b border-foreground/10 p-6 flex items-start justify-between">
            <div className="flex items-center gap-4">
              {currentVisitor.photo ? (
                <div className="relative group">
                  <img
                    src={`/${currentVisitor.photo}`}
                    alt={currentVisitor.name}
                    className="w-20 h-20 rounded-2xl object-cover border-2 border-primary/50 shadow-lg"
                    onError={(e) => {
                      (e.target as HTMLElement).style.display = 'none';
                    }}
                  />
                  <div className="absolute -bottom-1 -right-1 bg-emerald-500 rounded-full p-1 text-white shadow-md">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  </div>
                </div>
              ) : (
                <div className="w-20 h-20 rounded-2xl bg-foreground/10 border border-foreground/15 flex items-center justify-center text-2xl font-black text-white shadow-inner">
                  {currentVisitor.name ? currentVisitor.name.slice(0, 2).toUpperCase() : 'V'}
                </div>
              )}

              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-2xl font-black text-foreground dark:text-white tracking-tight">
                    {currentVisitor.name || 'Visitor Details'}
                  </h2>
                  <span className="font-mono text-xs font-bold px-2 py-0.5 rounded-full bg-foreground/10 text-primary border border-primary/20">
                    {currentVisitor.visitor_id}
                  </span>
                </div>
                
                <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <span className="px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-400 font-bold uppercase tracking-wider">
                    {currentVisitor.role || 'VISITOR'}
                  </span>
                  <span>•</span>
                  <span className="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 font-bold uppercase tracking-wider">
                    {currentVisitor.status || 'REGISTERED'}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={async () => {
                  try {
                    await api.post('/api/face/watchlist', {
                      person_id: currentVisitor.visitor_id,
                      category: 'BLACKLIST',
                      severity: 'critical',
                      reason: `Flagged via visitor portal for ${currentVisitor.name}`
                    });
                    alert(`✅ ${currentVisitor.name} (${currentVisitor.visitor_id}) has been added to the Security Watchlist!`);
                  } catch (err: any) {
                    alert(err?.response?.data?.detail || "Failed to add to watchlist");
                  }
                }}
                className="px-3 py-1.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/40 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 shadow-sm"
              >
                <ShieldCheck className="w-3.5 h-3.5" /> Flag on Watchlist
              </button>

              <button
                onClick={onClose}
                className="p-2 rounded-xl bg-foreground/10 hover:bg-foreground/20 text-muted-foreground hover:text-white transition-all"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Body Content */}
          <div className="p-6 space-y-6 overflow-y-auto custom-scrollbar flex-1">
            {/* Quick Metrics */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-foreground/5 border border-foreground/10 rounded-2xl p-4 text-center">
                <div className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Total Visits</div>
                <div className="text-2xl font-black text-primary">
                  {currentVisitor.total_visits || 0}
                </div>
              </div>

              <div className="bg-foreground/5 border border-foreground/10 rounded-2xl p-4 text-center">
                <div className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Biometrics</div>
                <div className="text-xs font-bold text-emerald-400 flex items-center justify-center gap-1 mt-1.5">
                  <Sparkles className="w-3.5 h-3.5" /> 512D Active
                </div>
              </div>

              <div className="bg-foreground/5 border border-foreground/10 rounded-2xl p-4 text-center">
                <div className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Pass Status</div>
                <div className="text-xs font-bold text-blue-400 flex items-center justify-center gap-1 mt-1.5">
                  <ShieldCheck className="w-3.5 h-3.5" /> Verified
                </div>
              </div>
            </div>

            {/* Information Grid */}
            <div className="bg-foreground/5 border border-foreground/10 rounded-2xl p-5 space-y-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
                <User className="w-4 h-4 text-primary" /> Profile Information
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-foreground/5 text-muted-foreground">
                    <Mail className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-[10px] uppercase font-bold text-muted-foreground">Email Address</div>
                    <div className="font-medium text-foreground dark:text-white truncate">
                      {currentVisitor.email || 'Not provided'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-foreground/5 text-muted-foreground">
                    <Phone className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-[10px] uppercase font-bold text-muted-foreground">Phone Number</div>
                    <div className="font-medium text-foreground dark:text-white">
                      {currentVisitor.phone || 'Not provided'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-foreground/5 text-muted-foreground">
                    <Calendar className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-[10px] uppercase font-bold text-muted-foreground">Registered On</div>
                    <div className="font-medium text-foreground dark:text-white">
                      {currentVisitor.created_at ? new Date(currentVisitor.created_at).toLocaleString() : 'Recent'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-foreground/5 text-muted-foreground">
                    <Clock className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-[10px] uppercase font-bold text-muted-foreground">Last Activity</div>
                    <div className="font-medium text-foreground dark:text-white">
                      {currentVisitor.last_seen ? new Date(currentVisitor.last_seen).toLocaleString() : 'No visits recorded yet'}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* QR Pass Section */}
            <div className="bg-foreground/5 border border-foreground/10 rounded-2xl p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-4 text-center sm:text-left">
                <div className="bg-white p-2.5 rounded-xl shadow-md shrink-0">
                  <img
                    src={`https://api.qrserver.com/v1/create-qr-code/?size=100x100&data=${encodeURIComponent(`HERO_HOMES_VISITOR:${currentVisitor.visitor_id}`)}`}
                    alt="Visitor QR Pass"
                    className="w-16 h-16 object-contain"
                  />
                </div>
                <div>
                  <h4 className="font-bold text-foreground dark:text-white text-sm flex items-center gap-1.5">
                    <QrCode className="w-4 h-4 text-primary" /> Instant Gate QR Pass
                  </h4>
                  <p className="text-xs text-muted-foreground mt-0.5 max-w-xs">
                    This QR pass can be scanned at the security guard post or auto-turnstiles.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto">
                <button
                  onClick={() => window.print()}
                  className="flex-1 sm:flex-initial px-3.5 py-2 bg-foreground/10 hover:bg-foreground/20 rounded-xl text-xs font-bold text-foreground dark:text-white transition-all flex items-center justify-center gap-1.5"
                >
                  <Printer className="w-3.5 h-3.5" /> Print
                </button>
                <button
                  onClick={handleSendWhatsApp}
                  className="flex-1 sm:flex-initial px-3.5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 shadow-md shadow-emerald-600/20"
                >
                  <Send className="w-3.5 h-3.5" /> WhatsApp
                </button>
              </div>
            </div>

            {/* Visit History Log */}
            <div className="space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <History className="w-4 h-4 text-primary" /> Recent Entry / Exit History
              </h3>

              {history.length === 0 ? (
                <div className="p-6 text-center text-muted-foreground text-xs bg-foreground/5 rounded-2xl border border-foreground/5 flex flex-col items-center justify-center gap-1.5">
                  <Camera className="w-6 h-6 opacity-40" />
                  <span>No physical camera entry events detected yet for this visitor.</span>
                </div>
              ) : (
                <div className="space-y-2">
                  {history.map((h, i) => (
                    <div key={h.visit_id || i} className="flex items-center justify-between p-3 rounded-xl bg-background/50 border border-foreground/10 text-xs">
                      <div className="flex items-center gap-2.5">
                        <div className="w-2 h-2 rounded-full bg-emerald-400" />
                        <div>
                          <span className="font-bold text-foreground dark:text-white">{h.camera_id || 'Entrance Camera'}</span>
                          <span className="text-muted-foreground ml-2">{h.entry_time ? new Date(h.entry_time).toLocaleString() : 'Recent'}</span>
                        </div>
                      </div>
                      <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-foreground/10 text-muted-foreground">
                        {h.duration ? `${Math.round(h.duration / 60)} mins` : 'Active'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};

export default VisitorDetailModal;
