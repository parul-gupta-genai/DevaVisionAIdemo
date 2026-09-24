import React from 'react'
import { LayoutDashboard, Video, PlaySquare, AlertTriangle, BarChart2, Map, Users, Settings, LifeBuoy, Server, Database, ChevronLeft, ChevronRight, Trash2, Clock, Car, BadgeCheck, Flame, UserCheck, UserPlus, ShieldAlert, Box, ScanFace, Eye, ListChecks, HardHat, Shapes, Contact, Search, Home, Monitor, MapPin, Calendar, Truck, Shield, ClipboardList, EyeOff, Camera, Tag, CalendarCheck, CheckCircle, Star, Download, ShieldCheck } from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import { cn } from '@/utils/utils'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { motion, AnimatePresence } from 'framer-motion'


const navGroups = [
  {
    title: 'Overview',
    items: [
      { icon: Home, label: 'Dashboard', path: '/' },
      { icon: Video, label: 'Live Cameras', path: '/cameras' },
      { icon: AlertTriangle, label: 'Events', path: '/events' },
      { icon: BarChart2, label: 'Analytics', path: '/analytics' },
    ],
  },
  {
    title: 'Safety',
    items: [
      { icon: Flame, label: 'Fire & Smoke', path: '/fire' },
      { icon: HardHat, label: 'PPE Monitoring', path: '/ppe' },
      { icon: Shapes, label: 'Restricted Zones', path: '/restricted-zones' },
    ],
  },
  {
    title: 'People',
    items: [
      { icon: BadgeCheck, label: 'Attendance', path: '/attendance' },
      { icon: UserPlus, label: 'Employee Directory', path: '/employee-db' },
      { icon: ScanFace, label: 'Face Watchlist', path: '/face-watchlist' },
      { icon: Users, label: 'Visitors', path: '/visitors' },
    ],
  },
  {
    title: 'Assets',
    items: [
      { icon: Car, label: 'Vehicles & ANPR', path: '/vehicles' },
      { icon: Box, label: 'Materials', path: '/materials' },
    ],
  },
];


const bottomNavItems = [
  { icon: Settings, label: 'Settings', path: '/settings' },
]

// Google-style gradient per section heading
const GROUP_GRADIENTS: Record<string, string> = {
  'Overview': 'linear-gradient(90deg, #4285F4, #34A853)',
  'Safety':   'linear-gradient(90deg, #EA4335, #FBBC05)',
  'People':   'linear-gradient(90deg, #34A853, #4285F4)',
  'Assets':   'linear-gradient(90deg, #FBBC05, #EA4335)',
}

function groupGradientStyle(title: string): React.CSSProperties {
  const gradient = GROUP_GRADIENTS[title] ?? 'linear-gradient(90deg, #90caf9, #e3f2fd)'
  return {
    background: gradient,
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  }
}


export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useAppStore()
  const location = useLocation()
  const { user } = useAuth()
  
  const isAdmin = user?.roles?.includes('admin') || user?.is_superuser

  const filteredNavGroups = navGroups.map(group => ({
    ...group,
    items: group.items.filter(item => {
      if (['Storage', 'AI Models'].includes(item.label) && !isAdmin) return false;
      return true;
    })
  })).filter(group => group.items.length > 0);

  const filteredBottomNavItems = bottomNavItems.filter(item => {
    if (['Users'].includes(item.label) && !isAdmin) return false;
    return true;
  });

  return (
    <motion.aside 
      layout
      className={cn(
          "text-white border-r border-white/10 flex flex-col justify-between shrink-0 h-full relative z-40 overflow-visible shadow-2xl transition-all duration-300",
          sidebarOpen ? "w-64" : "w-20"
        )}
      style={{ backgroundColor: '#1a237e' }}
      initial={false}
      animate={{ width: sidebarOpen ? 256 : 80 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
    >
      <div className="flex flex-col py-4 gap-4 overflow-y-auto custom-scrollbar flex-1 px-3">
        {filteredNavGroups.map((group, groupIndex) => {
          return (
          <div key={group.title} className="flex flex-col gap-1">
            {sidebarOpen && (
              <motion.div 
                initial={{ opacity: 0 }} 
                animate={{ opacity: 1 }} 
                className="px-4 py-1 text-[11px] font-bold uppercase tracking-wider"
                style={groupGradientStyle(group.title)}
              >
                {group.title}
              </motion.div>
            )}
            {!sidebarOpen && groupIndex > 0 && (
              <div className="h-px bg-white/10 mx-2 my-2" />
            )}
            {group.items.map((item) => {
              const isActive = location.pathname === item.path
              return (
                <Link 
                  key={item.label} 
                  to={item.path}
                  className="relative group"
                >
                  {isActive && (
                    <motion.div 
                      layoutId="activeTab"
                      className="absolute inset-0 bg-white/20 border border-white/30 rounded-xl shadow-md"
                      initial={false}
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  
                  <div className={cn(
                    "flex items-center gap-4 px-3 py-2.5 rounded-xl transition-all relative z-10 font-medium",
                    isActive ? "text-white font-bold" : "text-blue-100/80 hover:text-white hover:bg-white/10"
                  )}>
                    {isActive && <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-white rounded-r-md shadow-sm" />}
                    
                    <motion.div whileHover={{ scale: 1.1, rotate: isActive ? 0 : 5 }} whileTap={{ scale: 0.95 }}>
                      <item.icon className={cn(
                        "w-5 h-5 shrink-0 transition-colors", 
                        isActive ? "text-white drop-shadow-[0_0_8px_rgba(255,255,255,0.7)]" : "text-blue-200"
                      )} />
                    </motion.div>
                    
                    <AnimatePresence>
                      {sidebarOpen && (
                        <motion.span 
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, x: -10 }}
                          transition={{ duration: 0.2 }}
                          className="font-medium whitespace-nowrap tracking-wide text-sm"
                        >
                          {item.label}
                        </motion.span>
                      )}
                    </AnimatePresence>
                  </div>
                </Link>
              )
            })}
          </div>
        )})}
      </div>

      <div className="flex flex-col py-4 gap-2 border-t border-white/10 px-3">
        {filteredBottomNavItems.map((item) => {
          const isActive = location.pathname === item.path
          return (
            <Link 
              key={item.label} 
              to={item.path}
              className={cn(
                "flex items-center gap-4 px-3 py-3 rounded-xl transition-all relative group",
                isActive ? "text-white bg-white/20 border border-white/30 font-bold" : "text-blue-100/80 hover:text-white hover:bg-white/10"
              )}
            >
              <motion.div whileHover={{ rotate: 15 }} whileTap={{ scale: 0.9 }}>
                <item.icon className={cn("w-5 h-5 shrink-0", isActive ? "text-white drop-shadow-[0_0_8px_rgba(255,255,255,0.7)]" : "text-blue-200")} />
              </motion.div>
              <AnimatePresence>
                {sidebarOpen && (
                  <motion.span 
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -10 }}
                    className="font-medium whitespace-nowrap tracking-wide text-sm"
                  >
                    {item.label}
                  </motion.span>
                )}
              </AnimatePresence>
            </Link>
          )
        })}
        
        <button 
          onClick={toggleSidebar}
          className="flex items-center gap-4 px-3 py-3 mt-2 rounded-xl text-blue-100/80 hover:bg-white/10 hover:text-white transition-all group cursor-pointer"
        >
          <motion.div whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }}>
            {sidebarOpen ? <ChevronLeft className="w-5 h-5 shrink-0 text-blue-200" /> : <ChevronRight className="w-5 h-5 shrink-0 text-blue-200" />}
          </motion.div>
          <AnimatePresence>
            {sidebarOpen && (
              <motion.span 
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                className="font-medium whitespace-nowrap tracking-wide"
              >
                Collapse
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </motion.aside>
  )
}
