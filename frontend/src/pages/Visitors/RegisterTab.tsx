import React, { useRef, useState } from 'react';
import { Camera, QrCode, CheckCircle2, UserPlus, Smartphone, Send, Copy, ExternalLink, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useToastStore } from '@/store/useToastStore';

export default function RegisterTab() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [isGenerated, setIsGenerated] = useState(false);
  const { addToast } = useToastStore();

  // Form states
  const [fullName, setFullName] = useState('');
  const [mobileNumber, setMobileNumber] = useState('');
  const [email, setEmail] = useState('');
  const [idNumber, setIdNumber] = useState('');
  const [hostName, setHostName] = useState('');
  const [flat, setFlat] = useState('');
  const [purpose, setPurpose] = useState('meeting');
  
  // Mobile QR Modal state
  const [showMobileQRModal, setShowMobileQRModal] = useState(false);
  const [networkHost, setNetworkHost] = useState(localStorage.getItem('devavision_mobile_host') || '192.168.1.8');

  React.useEffect(() => {
    // Fetch real network IP from backend
    fetch('/api/system/network-info')
      .then((res) => res.json())
      .then((data) => {
        if (data?.local_ip && data.local_ip !== '127.0.0.1') {
          setNetworkHost((prev) => {
            if (!localStorage.getItem('devavision_mobile_host')) {
              return data.local_ip;
            }
            return prev;
          });
        }
      })
      .catch(() => {});
  }, []);

  const getMobileRegisterUrl = () => {
    // Never use 'localhost' or '127.0.0.1' for mobile links
    let host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      host = networkHost || '192.168.1.8';
    }
    const port = window.location.port ? `:${window.location.port}` : ':3000';
    const params = new URLSearchParams();
    if (fullName) params.set('name', fullName);
    if (mobileNumber) params.set('mobile', mobileNumber);
    return `${window.location.protocol}//${host}${port}/register?${params.toString()}`;
  };

  const handleSaveHost = (newHost: string) => {
    setNetworkHost(newHost);
    localStorage.setItem('devavision_mobile_host', newHost);
  };

  const handleSendWhatsAppLink = () => {
    if (!mobileNumber) {
      addToast({ title: 'Mobile Number Required', message: 'Please enter visitor mobile number first.', type: 'danger' });
      return;
    }
    const cleanMobile = mobileNumber.replace(/\D/g, '');
    const mobileWithCountry = cleanMobile.length === 10 ? `91${cleanMobile}` : cleanMobile;
    const registerUrl = getMobileRegisterUrl();
    const msg = encodeURIComponent(
      `Namaste ${fullName || 'Visitor'},\n\nPlease complete your visitor check-in and 3-angle face photo here:\n👉 ${registerUrl}\n\nThank you,\nDevaVision AI Security`
    );
    window.open(`https://wa.me/${mobileWithCountry}?text=${msg}`, '_blank');
    addToast({ title: 'WhatsApp Opened', message: `Self-checkin link ready for ${fullName || mobileNumber}`, type: 'success' });
  };

  const handleCopyLink = () => {
    const url = getMobileRegisterUrl();
    navigator.clipboard.writeText(url);
    addToast({ title: 'Link Copied', message: 'Mobile self-registration link copied to clipboard!', type: 'success' });
  };

  const handlePhoto = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      setPreview(URL.createObjectURL(e.target.files[0]));
    }
  };

  const handleRegister = (e: React.FormEvent) => {
    e.preventDefault();
    setIsGenerated(true);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 glass border border-foreground/10 rounded-2xl p-6 md:p-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <UserPlus className="w-5 h-5 text-primary" /> Register New Visitor
          </h2>

          {/* Quick Mobile Action Buttons */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowMobileQRModal(true)}
              className="px-3 py-1.5 bg-primary/15 hover:bg-primary/25 text-primary border border-primary/30 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 shadow-sm"
            >
              <Smartphone className="w-3.5 h-3.5" /> Scan on Mobile
            </button>
            <button
              type="button"
              onClick={handleSendWhatsAppLink}
              className="px-3 py-1.5 bg-success/15 hover:bg-success/25 text-success border border-success/30 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 shadow-sm"
            >
              <Send className="w-3.5 h-3.5" /> WhatsApp Link
            </button>
          </div>
        </div>
        
        <form onSubmit={handleRegister} className="space-y-6">
          <div className="flex flex-col md:flex-row gap-6">
            <div className="flex-1 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Full Name</label>
                  <input
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Enter name"
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Mobile Number</label>
                  <input
                    required
                    value={mobileNumber}
                    onChange={(e) => setMobileNumber(e.target.value)}
                    placeholder="Enter mobile (e.g. 9876543210)"
                    type="tel"
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Email (Optional)</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter email"
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">ID / Reference Number</label>
                  <input
                    required
                    value={idNumber}
                    onChange={(e) => setIdNumber(e.target.value)}
                    placeholder="Aadhaar / Driving License"
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                  />
                </div>
              </div>

              <div className="h-px w-full bg-foreground/10 my-4" />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Person to Meet (Host)</label>
                  <input
                    required
                    value={hostName}
                    onChange={(e) => setHostName(e.target.value)}
                    placeholder="Host Name"
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Flat / Building / Department</label>
                  <input
                    required
                    value={flat}
                    onChange={(e) => setFlat(e.target.value)}
                    placeholder="e.g. Tower A, Flat 402"
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Purpose of Visit</label>
                  <select
                    required
                    value={purpose}
                    onChange={(e) => setPurpose(e.target.value)}
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                  >
                    <option value="meeting">Meeting</option>
                    <option value="delivery">Delivery</option>
                    <option value="maintenance">Maintenance</option>
                    <option value="personal">Personal</option>
                    <option value="other">Other</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Expected In-Time (Date & Time)</label>
                  <input
                    required
                    type="datetime-local"
                    defaultValue={new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)}
                    className="w-full bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all [color-scheme:dark]"
                  />
                </div>
              </div>
            </div>

            <div className="shrink-0 flex flex-col items-center gap-4">
              <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider w-full text-center">Visitor Photo</label>
              <div 
                onClick={() => fileRef.current?.click()}
                className="w-48 h-48 rounded-2xl border-2 border-dashed border-primary/40 bg-primary/5 hover:bg-primary/10 transition-colors flex flex-col items-center justify-center cursor-pointer overflow-hidden shadow-inner group"
              >
                {preview ? (
                  <img src={preview} alt="Visitor" className="w-full h-full object-cover" />
                ) : (
                  <div className="flex flex-col items-center text-primary/60 group-hover:text-primary transition-colors">
                    <Camera className="w-8 h-8 mb-2" />
                    <span className="text-xs font-bold text-center px-4">Click to Capture<br/>or Upload Photo</span>
                  </div>
                )}
              </div>
              <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handlePhoto} />
            </div>
          </div>

          <div className="flex justify-end pt-4 border-t border-foreground/10">
            <button type="submit" className="px-8 py-3 rounded-xl bg-primary text-sm font-black text-white hover:bg-primary-600 transition-all shadow-lg shadow-primary/25">
              Generate QR Pass
            </button>
          </div>
        </form>
      </div>

      {/* Right Side: Pass Display */}
      <div className="glass border border-foreground/10 rounded-2xl p-6 flex flex-col items-center justify-center text-center">
        {isGenerated ? (
          <motion.div 
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="flex flex-col items-center w-full"
          >
            <div className="w-16 h-16 rounded-full bg-success/20 text-success flex items-center justify-center mb-4">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-bold text-white mb-2">Registration Complete</h3>
            <p className="text-sm text-muted-foreground mb-6">Visitor pass has been generated successfully.</p>
            
            <div className="bg-white p-4 rounded-xl mb-6 shadow-xl flex items-center justify-center">
              <QrCode className="w-48 h-48 text-black" />
            </div>

            <div className="grid grid-cols-2 w-full gap-2 text-left mb-6 text-sm">
              <div className="text-muted-foreground text-xs uppercase font-bold">Visitor</div>
              <div className="font-bold text-white text-right truncate">{fullName || 'Visitor'}</div>
              <div className="text-muted-foreground text-xs uppercase font-bold">Pass ID</div>
              <div className="font-mono text-white text-right">#VIS-{Math.floor(10000 + Math.random() * 90000)}</div>
              <div className="text-muted-foreground text-xs uppercase font-bold">Host / Flat</div>
              <div className="text-white text-right truncate">{hostName || 'Host'} ({flat || 'Site'})</div>
            </div>

            <div className="flex gap-2 w-full">
              <button
                type="button"
                onClick={() => window.print()}
                className="flex-1 py-2 rounded-lg bg-foreground/10 text-white text-sm font-bold hover:bg-foreground/20 transition-all"
              >
                Print Pass
              </button>
              <button
                type="button"
                onClick={handleSendWhatsAppLink}
                className="flex-1 py-2 rounded-lg bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 text-sm font-bold hover:bg-indigo-500/30 transition-all flex items-center justify-center gap-1.5"
              >
                <Send className="w-3.5 h-3.5" /> Share on WhatsApp
              </button>
            </div>
          </motion.div>
        ) : (
          <div className="text-muted-foreground flex flex-col items-center opacity-50">
            <QrCode className="w-16 h-16 mb-4" />
            <p className="text-sm font-medium">QR Pass will appear here after registration.</p>
          </div>
        )}
      </div>

      {/* Mobile QR Scan Modal */}
      {showMobileQRModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-fadeIn">
          <div className="bg-background border border-foreground/15 rounded-3xl p-6 w-full max-w-sm space-y-5 shadow-2xl text-center relative">
            <button
              onClick={() => setShowMobileQRModal(false)}
              className="absolute top-4 right-4 p-1.5 rounded-lg bg-foreground/10 text-muted-foreground hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex flex-col items-center">
              <div className="p-3 bg-primary/15 text-primary rounded-2xl mb-3">
                <Smartphone className="w-6 h-6" />
              </div>
              <h3 className="font-bold text-lg text-white">Scan with Mobile Phone</h3>
              <p className="text-xs text-muted-foreground mt-1">
                Point your phone camera at this QR code to open 3-angle face capture on your mobile.
              </p>
            </div>

            {/* QR Code */}
            <div className="bg-white p-4 rounded-2xl shadow-xl mx-auto inline-block">
              <img
                src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(getMobileRegisterUrl())}`}
                alt="Scan to Register on Phone"
                className="w-44 h-44 object-contain rounded-lg"
              />
            </div>

            {/* Editable Host IP Field */}
            <div className="text-left space-y-1 bg-foreground/5 p-3 rounded-xl border border-foreground/10">
              <label className="text-[10px] font-bold text-muted-foreground uppercase">Server IP / Host for Mobile</label>
              <input
                type="text"
                value={networkHost}
                onChange={(e) => handleSaveHost(e.target.value)}
                placeholder="192.168.1.8 or domain"
                className="w-full bg-background/80 border border-foreground/20 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-primary font-mono"
              />
            </div>

            <div className="space-y-2 pt-2">
              <button
                onClick={handleCopyLink}
                className="w-full py-2.5 rounded-xl bg-foreground/10 hover:bg-foreground/20 text-white text-xs font-bold transition-all flex items-center justify-center gap-1.5"
              >
                <Copy className="w-3.5 h-3.5" /> Copy Mobile Link
              </button>
              <a
                href={getMobileRegisterUrl()}
                target="_blank"
                rel="noreferrer"
                className="w-full py-2 rounded-xl text-primary text-xs font-bold hover:underline flex items-center justify-center gap-1"
              >
                <ExternalLink className="w-3.5 h-3.5" /> Open Link in Browser Tab
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
