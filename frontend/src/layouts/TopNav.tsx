import { Search, Bell, Settings, Maximize, User, Moon, Sun, LogOut, Activity, Palette, Fingerprint } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '@/store/useAppStore'
import { useState, useEffect } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '@/api/api'
import SystemHealthModal from '@/components/system/SystemHealthModal'

import { useProjectConfigStore } from '@/store/useProjectConfigStore'

export function TopNav() {
  const navigate = useNavigate()
  const { theme, cycleTheme, toggleRightPanel, toggleAIChat } = useAppStore()
  const { timezone } = useProjectConfigStore()
  const { user, logout } = useAuth()
  const [time, setTime] = useState(new Date())
  const [tele, setTele] = useState<any>(null)
  const [healthModalOpen, setHealthModalOpen] = useState(false)

  const isAdmin = user?.roles?.includes('admin') || user?.is_superuser

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    const fetchTele = () => {
      api.get('/telemetry')
        .then(res => {
          setTele(res.data)
        })
        .catch(() => {})
    }
    fetchTele()
    const timer = setInterval(fetchTele, 2000)
    return () => clearInterval(timer)
  }, [])

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen()
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen()
      }
    }
  }

  return (
    <header className="h-16 glass-pro z-50 flex items-center justify-between px-6 shrink-0 relative border-b border-white/[0.05]">
      
      {/* Decorative Top Highlight */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-primary/50 to-transparent opacity-50" />

      {/* Left */}
      <div className="flex items-center gap-8 w-1/3">
        <motion.div 
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex items-center gap-3 cursor-pointer group"
        >
          <div className="relative flex items-center justify-center">
             <img src="/Hero_Homes.png" alt="Hero Homes Logo" className="w-auto h-8 rounded relative z-10" />
          </div>
          <span className="font-bold text-lg tracking-widest uppercase text-foreground dark:text-transparent dark:bg-clip-text dark:bg-gradient-to-r dark:from-white dark:to-white/70">
            Hero Homes
          </span>
        </motion.div>
        
        <div className="relative hidden md:block w-72 group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
            <input 
              type="text" 
              placeholder="Command / Search cameras..." 
              className="w-48 md:w-48 max-w-xs bg-muted/80 backdrop-blur-md border border-border/80 dark:border-foreground/10 rounded-md py-1 pl-5 pr-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all text-foreground dark:text-white placeholder:text-muted-foreground/70 shadow-inner" 
            />
          <div className="absolute top-1/2 -translate-y-1/2 flex items-center gap-1" style={{ right: '-12px' }}>
            <kbd className="hidden sm:inline-flex items-center gap-1 ml-2 rounded border border-foreground/10 bg-foreground/5 px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
              <span className="text-xs">⌘</span>K
            </kbd>
          </div>
          {/* Horizontal display of CPU / RAM / GPU metrics */}
          <div
            onClick={() => setHealthModalOpen(true)}
            className="hidden lg:flex items-center gap-4 mr-4 text-[10px] font-medium text-muted-foreground uppercase tracking-widest cursor-pointer"
          >
            {/* CPU */}
            <div className="flex items-center gap-1">
              <span>CPU</span>
              <span className="text-[#1A73E8] dark:text-primary font-bold">
                {tele?.cpu_usage != null ? `${Math.round(tele.cpu_usage)}%` : '--'}
              </span>
            </div>
            {/* RAM */}
            <div className="flex items-center gap-1">
              <span>RAM</span>
              <span className="text-[#9334E6] dark:text-accent font-bold">
                {tele?.ram_usage != null ? `${Math.round(tele.ram_usage)}%` : '--'}
              </span>
            </div>
            {/* GPU */}
            <div className="flex items-center gap-1">
              <span>GPU</span>
              <span className="text-[#1E8E3E] dark:text-white font-bold">
                {tele?.gpu_usage != null ? `${Math.round(tele.gpu_usage)}%` : '--'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Center - Status & Time */}
      <div className="hidden lg:flex items-center justify-center gap-8 w-1/3 text-sm text-muted-foreground">
        <motion.div 
          whileHover={{ scale: 1.05 }}
          className="flex items-center gap-2 bg-success/10 px-3 py-1 rounded-full border border-success/20"
        >
          <div className="w-2 h-2 rounded-full bg-success animate-pulse glow-success shadow-[0_0_8px_var(--color-success)]" />
          <span className="text-success font-medium text-xs tracking-wider uppercase">System Healthy</span>
        </motion.div>
        <div className="flex flex-col items-center">
          <span className="text-foreground font-semibold tracking-widest tabular-nums drop-shadow-md">
            {time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: timezone || 'Asia/Kolkata' })}
          </span>
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest">
            {time.toLocaleDateString([], { timeZone: timezone || 'Asia/Kolkata' })}
          </span>
        </div>
      </div>

      {/* Right */}
      <div className="flex items-center justify-end gap-3 w-1/3">
        
        <motion.button 
          whileHover={{ scale: 1.05 }} 
          whileTap={{ scale: 0.95 }} 
          onClick={toggleAIChat}
          className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/20 hover:bg-primary/30 border border-primary/30 transition-colors text-primary font-bold text-xs"
        >
          <Fingerprint className="w-4 h-4 animate-pulse" />
          <span>AI Assistant</span>
        </motion.button>

        <motion.button 
          whileHover={{ scale: 1.1 }} 
          whileTap={{ scale: 0.95 }} 
          onClick={cycleTheme} 
          className="relative w-9 h-9 flex items-center justify-center rounded-full bg-foreground/5 hover:bg-foreground/10 border border-foreground/5 transition-colors overflow-hidden group"
          title={`Current Theme: ${theme.charAt(0).toUpperCase() + theme.slice(1)}`}
        >
          <AnimatePresence mode="wait">
            {theme === 'dark' && (
              <motion.div key="dark" initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1, rotate: 0 }} exit={{ y: -20, opacity: 0, rotate: -45 }} transition={{ duration: 0.2 }}>
                <Moon className="w-4 h-4 text-primary" />
              </motion.div>
            )}
            {theme === 'light' && (
              <motion.div key="light" initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1, rotate: 0 }} exit={{ y: -20, opacity: 0, rotate: 45 }} transition={{ duration: 0.2 }}>
                <Sun className="w-4 h-4 text-warning" />
              </motion.div>
            )}
            {theme === 'colorful' && (
              <motion.div key="colorful" initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1, rotate: 360 }} exit={{ scale: 0, opacity: 0 }} transition={{ duration: 0.4 }}>
                <Palette className="w-4 h-4 text-accent" />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.button>
        
        <motion.button whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.95 }} onClick={toggleFullscreen} className="p-2 rounded-full bg-foreground/5 hover:bg-foreground/10 border border-foreground/5 transition-colors text-muted-foreground hover:text-foreground">
          <Maximize className="w-4 h-4" />
        </motion.button>
        
        <motion.button whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.95 }} onClick={toggleRightPanel} className="relative p-2 rounded-full bg-foreground/5 hover:bg-foreground/10 border border-foreground/5 transition-colors text-muted-foreground hover:text-foreground">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-danger animate-pulse glow-danger" />
        </motion.button>
        
        {isAdmin && (
          <motion.button whileHover={{ scale: 1.1, rotate: 90 }} whileTap={{ scale: 0.95 }} onClick={() => navigate('/settings')} className="p-2 rounded-full bg-foreground/5 hover:bg-foreground/10 border border-foreground/5 transition-colors text-muted-foreground hover:text-foreground">
            <Settings className="w-4 h-4" />
          </motion.button>
        )}
        
        <div className="flex items-center gap-3 ml-2 border-l border-foreground/10 pl-5">
          <div className="flex flex-col items-end hidden sm:flex">
            <span className="text-sm font-semibold text-foreground tracking-wide">{user?.email || 'Admin'}</span>
            <span className="text-[10px] text-primary uppercase tracking-widest">{user?.roles?.[0] || 'Administrator'}</span>
          </div>
          <motion.div whileHover={{ scale: 1.1 }} className="h-9 w-9 rounded-full bg-primary/20 border border-primary/50 flex items-center justify-center cursor-pointer hover:bg-primary/30 transition-all glow-primary">
            <User className="w-4 h-4 text-primary" />
          </motion.div>
          <motion.button 
            whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.95 }}
            onClick={logout}
            className="p-2 ml-1 rounded-full hover:bg-danger/20 hover:border-danger/50 border border-transparent transition-all text-muted-foreground hover:text-danger group"
            title="Logout"
          >
            <LogOut className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
          </motion.button>
        </div>
      </div>

      <AnimatePresence>
        {healthModalOpen && <SystemHealthModal isOpen={healthModalOpen} onClose={() => setHealthModalOpen(false)} />}
      </AnimatePresence>
    </header>
  )
}
