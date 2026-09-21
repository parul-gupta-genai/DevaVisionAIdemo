import os
import sys

BASE_DIR = "/home/user/DevaVisionAI"
if not os.path.exists(BASE_DIR):
    if os.path.exists("frontend") and os.path.exists("backend"):
        BASE_DIR = os.getcwd()
    else:
        print(f"Error: Base directory {BASE_DIR} not found.")
        sys.exit(1)

print(f"Applying full integration patch to {BASE_DIR}...")

# 1. Database ORM Models
os.makedirs(os.path.join(BASE_DIR, "backend/database/models"), exist_ok=True)

with open(os.path.join(BASE_DIR, "backend/database/models/__init__.py"), "w") as f:
    f.write("from database.models.models import Camera, CameraEvent\nfrom database.models.auth import User, Role, Permission, RefreshToken, AuditLog\n")

models_py = """from sqlalchemy import Column, Integer, String, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from database.session import Base

class Camera(Base):
    __tablename__ = "cameras"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    rtsp_url = Column(String, nullable=True)
    source_type = Column(String, nullable=False, default="rtsp")
    source = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    state = Column(String, nullable=True, default="STOPPED")
    edge_id = Column(String, nullable=True, default="edge-01")
    created_at = Column(DateTime(timezone=True), default=func.now())

class CameraEvent(Base):
    __tablename__ = "camera_events"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    events = Column(JSONB, nullable=False)
    __table_args__ = (Index("idx_camera_timestamp", "camera_id", "timestamp"),)
"""
with open(os.path.join(BASE_DIR, "backend/database/models/models.py"), "w") as f:
    f.write(models_py)

auth_models_py = """from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.session import Base

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    permissions = relationship("Permission", secondary=role_permissions, lazy="selectin")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    roles = relationship("Role", secondary=user_roles, lazy="selectin")

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=func.now())
"""
with open(os.path.join(BASE_DIR, "backend/database/models/auth.py"), "w") as f:
    f.write(auth_models_py)

print("✓ Database ORM models created.")

# 2. CartonAnalytics.tsx (Mock Elimination)
carton_tsx = """import { useMemo, useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Box, TrendingUp, ArrowUpRight, ArrowDownRight, PackageCheck, Activity, Camera } from 'lucide-react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts'
import { useCameraStateStore } from '@/store/useCameraStateStore'
import { cn } from '@/utils/utils'

export function CartonAnalytics() {
  const states = useCameraStateStore(state => state.states)
  const [history, setHistory] = useState<{ time: string; count: number }[]>([])
  const lastTotalRef = useRef<number>(0)

  const { totalCartons, activeConveyors, liveRate } = useMemo(() => {
    let total = 0
    let conveyors = 0

    Object.values(states || {}).forEach((camState: any) => {
      const pluginEvents = camState.events?.CartonCountingPlugin || []
      const statsEvent = pluginEvents.find((e: any) => e.event_type === 'CARTON_STATS')
      if (statsEvent?.metadata) {
        total += statsEvent.metadata.total_cartons_counted || 0
        conveyors += 1
      }
    })

    const rate = Math.max(0, total - lastTotalRef.current)
    lastTotalRef.current = total
    return { totalCartons: total, activeConveyors: conveyors, liveRate: rate }
  }, [states])

  useEffect(() => {
    const now = new Date()
    const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`

    setHistory(prev => {
      const updated = [...prev, { time: timeStr, count: totalCartons }]
      return updated.slice(-15)
    })
  }, [totalCartons])

  return (
    <div className="flex-1 p-8 overflow-y-auto custom-scrollbar h-full relative">
      <div className="absolute top-0 left-0 w-full h-96 bg-primary/5 blur-3xl -z-10 pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-96 h-96 bg-accent/5 blur-3xl -z-10 pointer-events-none" />

      <div className="max-w-7xl mx-auto space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-black tracking-tight text-white flex items-center gap-4 drop-shadow-sm">
              <Box className="w-10 h-10 text-primary drop-shadow-[0_0_15px_rgba(59,130,246,0.6)]" />
              Carton Analytics
            </h1>
            <p className="text-foreground/60 mt-2 font-medium">Real-time conveyor tracking, package counting, and supply chain telemetry.</p>
          </div>
          <div className="flex gap-4">
            <span className="glass-panel px-4 py-2 rounded-xl text-sm font-medium text-foreground/80 border border-foreground/10 flex items-center gap-2 shadow-lg">
              <span className={`w-2 h-2 rounded-full ${activeConveyors > 0 ? 'bg-success animate-pulse glow-success' : 'bg-warning'}`} />
              {activeConveyors > 0 ? `${activeConveyors} Active Stream${activeConveyors > 1 ? 's' : ''}` : 'Awaiting Streams'}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <KPICard title="Total Cartons Counted" value={totalCartons.toLocaleString()} trend="+100%" trendUp={true} icon={Box} color="text-primary" bg="bg-primary/10" borderColor="border-primary/20" />
          <KPICard title="Conveyor Lines Active" value={activeConveyors.toString()} trend={activeConveyors > 0 ? "Online" : "Idle"} trendUp={activeConveyors > 0} icon={Camera} color="text-success" bg="bg-success/10" borderColor="border-success/20" />
          <KPICard title="Live Flow Rate" value={`${liveRate} / sec`} trend="Real-Time" trendUp={liveRate > 0} icon={TrendingUp} color="text-warning" bg="bg-warning/10" borderColor="border-warning/20" />
          <KPICard title="Line Status" value={activeConveyors > 0 ? "Tracking" : "Standby"} trend="AI Vision" trendUp={activeConveyors > 0} icon={PackageCheck} color="text-accent" bg="bg-accent/10" borderColor="border-accent/20" />
        </div>

        <div className="glass-panel p-6 rounded-2xl border border-foreground/10 shadow-2xl relative overflow-hidden group">
          <div className="flex justify-between items-center mb-6 relative z-10">
            <h3 className="text-xl font-bold text-white flex items-center gap-2">
              <Activity className="w-5 h-5 text-primary" />
              Real-Time Conveyor Count History
            </h3>
            <span className="text-xs text-muted-foreground uppercase font-mono tracking-wider">Live WebSocket Feed</span>
          </div>
          <div className="h-[350px] w-full relative z-10">
            {history.length === 0 || (totalCartons === 0 && activeConveyors === 0) ? (
              <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-3">
                <Box className="w-12 h-12 opacity-20" />
                <p className="text-sm font-medium">No carton tracking activity detected. Start a camera with CartonCountingPlugin enabled.</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history.map(item => ({ ...item }))} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4}/>
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="time" stroke="rgba(255,255,255,0.3)" tick={{fill: 'rgba(255,255,255,0.5)', fontSize: 12}} tickLine={false} axisLine={false} />
                  <YAxis stroke="rgba(255,255,255,0.3)" tick={{fill: 'rgba(255,255,255,0.5)', fontSize: 12}} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px' }} itemStyle={{ color: '#fff' }} />
                  <Area type="monotone" dataKey="count" name="Cumulative Cartons" stroke="#3b82f6" strokeWidth={3} fillOpacity={1} fill="url(#colorCount)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function KPICard({ title, value, trend, trendUp, icon: Icon, color, bg, borderColor }: any) {
  return (
    <motion.div whileHover={{ y: -5, scale: 1.02 }} className={cn("glass-panel p-6 rounded-2xl border shadow-xl relative overflow-hidden group", borderColor)}>
      <div className={cn("absolute -right-6 -top-6 w-24 h-24 rounded-full blur-2xl opacity-50 group-hover:opacity-80 transition-opacity duration-500", bg)} />
      <div className="flex justify-between items-start mb-4 relative z-10">
        <div className={cn("p-3 rounded-xl", bg)}><Icon className={cn("w-6 h-6", color)} /></div>
        <div className={cn("flex items-center gap-1 text-sm font-bold px-2 py-1 rounded-full", trendUp ? "text-success bg-success/10" : "text-danger bg-danger/10")}>
          {trendUp ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
          {trend}
        </div>
      </div>
      <div className="relative z-10">
        <h4 className="text-foreground/50 font-medium text-sm mb-1">{title}</h4>
        <div className="text-3xl font-black text-white tracking-tight">{value}</div>
      </div>
    </motion.div>
  )
}
"""
with open(os.path.join(BASE_DIR, "frontend/src/pages/CartonAnalytics.tsx"), "w") as f:
    f.write(carton_tsx)

print("✓ CartonAnalytics.tsx connected to real WebSocket pipeline.")

# 3. VisitorAnalytics.tsx (API route fix)
v_path = os.path.join(BASE_DIR, "frontend/src/pages/VisitorAnalytics.tsx")
if os.path.exists(v_path):
    with open(v_path, "r") as f:
        v = f.read()
    v = v.replace("import axios from 'axios';", "import { api } from '@/api/api';")
    v = v.replace("/api/visitor/events/all", "/api/plugins/visitor/events/all")
    v = v.replace("axios.get(", "api.get(")
    with open(v_path, "w") as f:
        f.write(v)
    print("✓ VisitorAnalytics.tsx route fixed.")

# 4. FireAnalytics, ParkingAnalytics, AttendanceAnalytics (Token and fetch -> api fixes)
for page, endpoint in [
    ("FireAnalytics.tsx", "/api/fire/events"),
    ("ParkingAnalytics.tsx", "/api/parking/stats"),
    ("AttendanceAnalytics.tsx", "/api/attendance/stats")
]:
    p_path = os.path.join(BASE_DIR, "frontend/src/pages", page)
    if os.path.exists(p_path):
        with open(p_path, "r") as f:
            p = f.read()
        if "import { api } from '@/api/api'" not in p:
            p = "import { api } from '@/api/api'\n" + p
        p = p.replace(f"fetch('{endpoint}', {{\n          headers: {{\n            'Authorization': `Bearer ${{localStorage.getItem('token')}}`\n          }}\n        }})", f"api.get('{endpoint}')")
        p = p.replace("localStorage.getItem('token')", "localStorage.getItem('access_token')")
        with open(p_path, "w") as f:
            f.write(p)
        print(f"✓ {page} updated to central api client.")

# 5. LiveCameras/index.tsx (PUT -> POST config contract fix)
lc_path = os.path.join(BASE_DIR, "frontend/src/pages/LiveCameras/index.tsx")
if os.path.exists(lc_path):
    with open(lc_path, "r") as f:
        lc = f.read()
    lc = lc.replace(
        "await api.put('/api/config', {\n                CAMERA_PLUGINS: { [newCameraId]: selectedPlugins }\n              })",
        "await api.post('/api/config', {\n                updates: { CAMERA_PLUGINS: { [newCameraId]: selectedPlugins } }\n              })"
    )
    with open(lc_path, "w") as f:
        f.write(lc)
    print("✓ LiveCameras/index.tsx config API contract corrected.")

print("\n🚀 All updates applied successfully on Jetson Nano!")
