import { Save, Plus, Camera, Users, ShieldAlert, UserPlus, Loader2 } from 'lucide-react'
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useToastStore } from '@/store/useToastStore'
import { useAuth } from '../../contexts/AuthContext'
import { useUsers } from '../../api/hooks/useUsers'
import { api } from '../../api/api'
import { cn } from '@/utils/utils'
import { useAppStore } from '@/store/useAppStore'
import { OrganizationTab } from './tabs/OrganizationTab'
import { AIConfigTab } from './tabs/AIConfigTab'
import { AlertsTab } from './tabs/AlertsTab'
import { StorageTab } from './tabs/StorageTab'
import { SystemTab } from './tabs/SystemTab'
import { LicenseTab } from './tabs/LicenseTab'
import { VoiceAssistantTab } from './tabs/VoiceAssistantTab'

const TABS = [
  'Organization',
  'Cameras',
  'AI Configuration',
  'Voice Assistant',
  'Alerts',
  'People',
  'Storage',
  'System',
  'License'
]

function CameraStatusList() {
  const [statuses, setStatuses] = useState<Record<string, string>>({})
  
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await api.get('/api/cameras/status')
        if (res.data && typeof res.data === 'object' && !Array.isArray(res.data)) {
          setStatuses(res.data)
        } else {
          setStatuses({})
        }
      } catch (e) {
        console.error(e)
      }
    }
    fetchStatus()
    const int = setInterval(fetchStatus, 3000)
    return () => clearInterval(int)
  }, [])

  return (
    <div className="glass-panel p-6 rounded-2xl border border-foreground/10 relative overflow-hidden">
      <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-[40px] pointer-events-none -mt-10 -mr-10" />
      <h3 className="text-xs font-bold tracking-widest uppercase text-foreground mb-4 drop-shadow-md">Live Connections</h3>
      {Object.keys(statuses).length === 0 ? (
        <p className="text-sm text-muted-foreground italic">No cameras configured or backend unreachable.</p>
      ) : (
        <div className="space-y-3 relative z-10">
          {Object.entries(statuses).map(([url, status]) => (
            <div key={url} className="flex flex-col gap-1 bg-background/40 p-4 rounded-xl border border-foreground/5 hover:bg-background/60 transition-colors">
              <span className="text-sm font-medium truncate text-white" title={url}>{url}</span>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${status === 'Connected' ? 'bg-success animate-pulse glow-success' : 'bg-warning animate-pulse glow-warning'}`} />
                <span className={`text-[10px] font-bold tracking-widest uppercase ${status === 'Connected' ? 'text-success' : 'text-warning'}`}>{status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function Settings() {
  const [activeTab, setActiveTab] = useState('Organization')
  const [cameraName, setCameraName] = useState('')
  const [rtspUrl, setRtspUrl] = useState('')
  const [sourceType, setSourceType] = useState('rtsp')
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const { addToast } = useToastStore()
  const { user } = useAuth()
  
  const [newUserEmail, setNewUserEmail] = useState('')
  const [newUserPassword, setNewUserPassword] = useState('')
  const { users, roles, isLoading: usersLoading, fetchUsers, fetchRoles, createUser, assignRole, error: usersError } = useUsers()
  
  const [backendConfig, setBackendConfig] = useState<any>({})
  const [configLoading, setConfigLoading] = useState(true)
  
  const isAdmin = user?.is_superuser || user?.roles?.includes('users:manage')

  const visibleTabs = isAdmin ? TABS : TABS.filter(t => t !== 'People')

  useEffect(() => {
    if (activeTab === 'People' && isAdmin) {
      fetchUsers()
      fetchRoles()
    }
  }, [activeTab, isAdmin, fetchUsers, fetchRoles])

  useEffect(() => {
    if (isAdmin) {
      const loadConfig = async () => {
        try {
          const res = await api.get('/api/config')
          setBackendConfig(res.data)
        } catch (e) {
          addToast({ title: 'Config Error', message: 'Failed to load backend config', type: 'danger' })
        } finally {
          setConfigLoading(false)
        }
      }
      loadConfig()
    }
  }, [isAdmin, addToast])

  const handleSaveConfig = async () => {
    try {
      await api.post('/api/config', { updates: backendConfig })
      addToast({ title: 'Settings Saved', message: 'Global configuration has been updated successfully.', type: 'success' })
    } catch (e) {
      addToast({ title: 'Save Error', message: 'Failed to save config', type: 'danger' })
    }
  }

  const [selectedPlugins, setSelectedPlugins] = useState<string[]>([])

  const togglePluginSelection = (pluginId: string) => {
    setSelectedPlugins(prev => 
      prev.includes(pluginId) ? prev.filter(id => id !== pluginId) : [...prev, pluginId]
    )
  }

  const handleAddCamera = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!cameraName) return
    if (sourceType === 'rtsp' && !rtspUrl) return
    if (sourceType === 'video_file' && !videoFile && !rtspUrl) return

    setIsSubmitting(true)
    try {
      let finalSource = rtspUrl

      if (sourceType === 'video_file' && videoFile) {
        const formData = new FormData()
        formData.append('file', videoFile)
        const uploadRes = await api.post('/api/cameras/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })
        finalSource = uploadRes.data.file_path
      }

      const res = await api.post('/api/cameras', { 
        name: cameraName, 
        rtsp_url: finalSource,
        source_type: sourceType,
        source: finalSource
      })

      if (res.status === 200) {
        const newCamId = res.data?.camera_id
        if (newCamId && selectedPlugins.length > 0) {
          try {
            await api.post('/api/config', {
              updates: { CAMERA_PLUGINS: { [newCamId]: selectedPlugins } }
            })
          } catch (err) {
            console.error('Failed to set initial camera plugins:', err)
          }
        }
        addToast({ title: 'Camera Added', message: `Successfully connected to ${cameraName}`, type: 'success' })
        setCameraName('')
        setRtspUrl('')
        setVideoFile(null)
        setSelectedPlugins([])
      } else {
        throw new Error('Failed to add camera')
      }
    } catch (error) {
      addToast({ title: 'Connection Error', message: 'Could not connect to camera stream.', type: 'danger' })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="p-8 pb-24 h-full overflow-y-auto custom-scrollbar relative">
      <div className="absolute top-0 left-0 w-full h-96 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />

      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-between items-end mb-10 relative z-10"
      >
        <div>
          <h1 className="text-4xl font-extrabold tracking-tight mb-2 text-gradient">System Settings</h1>
          <p className="text-muted-foreground font-medium tracking-wide">Manage global configuration, cameras, and AI policies.</p>
        </div>
        <button onClick={handleSaveConfig} className="flex items-center gap-2 px-6 py-2.5 bg-primary text-white rounded-xl font-bold hover:bg-primary/90 transition-all shadow-lg glow-primary hover-lift">
          <Save className="w-4 h-4" /> Save Configuration
        </button>
        {/* Light / Dark toggle */}
        <button onClick={() => useAppStore.getState().toggleTheme()}
                className="flex items-center gap-2 px-4 py-2 bg-gray-200 dark:bg-gray-800 text-gray-800 dark:text-gray-200 rounded-md hover:bg-gray-300 dark:hover:bg-gray-700 transition-colors">
          {useAppStore.getState().theme === 'dark' ? '🌙 Dark' : '☀️ Light'}
        </button>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-5 gap-8 relative z-10">
        <div className="col-span-1 lg:col-span-1 flex flex-col gap-2">
          {visibleTabs.map((tab) => (
            <button 
              key={tab} 
              onClick={() => setActiveTab(tab)}
              className={cn(
                "text-left px-5 py-3 rounded-xl font-bold text-sm transition-all relative overflow-hidden group",
                activeTab === tab 
                  ? "bg-primary text-white shadow-lg glow-primary" 
                  : "text-blue-900/80 hover:text-blue-900 dark:text-muted-foreground dark:hover:text-white glass-panel border border-foreground/5 hover:border-foreground/20"
              )}
            >
              {activeTab === tab && (
                <motion.div layoutId="settingsTab" className="absolute inset-0 bg-foreground/10" />
              )}
              <span className="relative z-10">{tab}</span>
            </button>
          ))}
        </div>

        <div className="col-span-1 md:col-span-3 lg:col-span-4 glass-pro rounded-3xl p-8 border border-foreground/10 relative overflow-hidden min-h-[500px]">
          <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full blur-[60px] pointer-events-none -mr-20 -mt-20" />
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
          
          {activeTab === 'Organization' && <OrganizationTab />}
          
          {activeTab === 'AI Configuration' && (
            <AIConfigTab backendConfig={backendConfig} setBackendConfig={setBackendConfig} configLoading={configLoading} />
          )}

          {activeTab === 'Voice Assistant' && <VoiceAssistantTab />}
          {activeTab === 'Alerts' && <AlertsTab />}
          {activeTab === 'Storage' && <StorageTab />}
          {activeTab === 'System' && <SystemTab />}
          {activeTab === 'License' && <LicenseTab />}

          {activeTab === 'Cameras' && (
            <>
              <div className="flex items-center gap-2 mb-6">
                <Camera className="w-6 h-6 text-primary" />
                <h2 className="text-xl font-semibold">Camera Connections</h2>
              </div>
              <p className="text-sm text-muted-foreground mb-6">Manage RTSP streams and view connection status.</p>
              
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                {/* Add Camera Form */}
                <form onSubmit={handleAddCamera} className="space-y-6 max-w-md bg-muted/20 p-6 rounded-xl border border-border h-fit">
                  <h3 className="font-medium text-foreground mb-2">Connect New Camera</h3>
                  <div className="flex flex-col gap-2">
                    <label className="text-sm font-medium text-foreground">Camera Name</label>
                    <input 
                      type="text" 
                      value={cameraName}
                      onChange={(e) => setCameraName(e.target.value)}
                      placeholder="e.g. Front Gate" 
                      className="bg-background border border-border rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/50 w-full" 
                      required
                    />
                  </div>

                  <div className="flex flex-col gap-2">
                    <label className="text-sm font-medium text-foreground">Source Type</label>
                    <select
                      value={sourceType}
                      onChange={(e) => setSourceType(e.target.value)}
                      className="bg-background border border-border rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/50 w-full"
                    >
                      <option value="rtsp">RTSP Stream</option>
                      <option value="video_file">Local Video</option>
                      <option value="webcam">USB Camera</option>
                    </select>
                  </div>

                  {sourceType === 'rtsp' && (
                    <div className="flex flex-col gap-2">
                      <label className="text-sm font-medium text-foreground">RTSP URL</label>
                      <input 
                        type="text" 
                        value={rtspUrl}
                        onChange={(e) => setRtspUrl(e.target.value)}
                        placeholder="rtsp://admin:pass@192.168.1.100/stream" 
                        className="bg-background border border-border rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/50 w-full font-mono text-sm" 
                        required
                      />
                      <p className="text-xs text-muted-foreground">Credentials containing special characters will be automatically encoded.</p>
                    </div>
                  )}

                  {sourceType === 'webcam' && (
                    <div className="flex flex-col gap-2">
                      <label className="text-sm font-medium text-foreground">Camera Index</label>
                      <input 
                        type="text" 
                        value={rtspUrl}
                        onChange={(e) => setRtspUrl(e.target.value)}
                        placeholder="0 or 1" 
                        className="bg-background border border-border rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/50 w-full font-mono text-sm" 
                        required
                      />
                    </div>
                  )}

                  {sourceType === 'video_file' && (
                    <div className="flex flex-col gap-3">
                      <div className="flex flex-col gap-2">
                        <label className="text-sm font-medium text-foreground">Upload Video File</label>
                        <input 
                          type="file"
                          accept="video/mp4,video/avi,video/mkv,video/mov"
                          onChange={(e) => {
                            setVideoFile(e.target.files?.[0] || null)
                            if (e.target.files?.[0]) setRtspUrl('')
                          }}
                          className="bg-background border border-border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50 w-full text-sm"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="h-px bg-border flex-1" />
                        <span className="text-xs text-muted-foreground uppercase">OR</span>
                        <div className="h-px bg-border flex-1" />
                      </div>
                      <div className="flex flex-col gap-2">
                        <label className="text-sm font-medium text-foreground">Local Video File Path</label>
                        <input 
                          type="text" 
                          value={rtspUrl}
                          onChange={(e) => {
                            setRtspUrl(e.target.value)
                            if (e.target.value) setVideoFile(null)
                          }}
                          placeholder="/path/to/local/video.mp4 or videos/sample.mp4" 
                          className="bg-background border border-border rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/50 w-full font-mono text-sm" 
                        />
                        <p className="text-xs text-muted-foreground">Path to any local video file on the host machine.</p>
                      </div>
                    </div>
                  )}

                  <div className="flex flex-col gap-2 pt-2 border-t border-border/50">
                    <div className="flex justify-between items-center">
                      <label className="text-sm font-medium text-foreground">Select Analytics (Optional)</label>
                      <span className="text-xs text-muted-foreground">{selectedPlugins.length} selected</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 max-h-44 overflow-y-auto pr-1 custom-scrollbar">
                      {[
                        { id: "IntrusionDetectionPlugin", label: "Intrusion Detection" },
                        { id: "PPEDetectionPlugin", label: "PPE Safety" },
                        { id: "FireDetectionPlugin", label: "Fire & Smoke" },
                        { id: "FightDetectionPlugin", label: "Fight / Quarrel" },
                        { id: "ANPRPlugin", label: "ANPR Plate" },
                        { id: "PeopleCountingPlugin", label: "People Counting" },
                        { id: "ParkingAnalyticsPlugin", label: "Parking" },
                        { id: "AttendanceDetectionPlugin", label: "Face Attendance" },
                        { id: "VisitorPlugin", label: "Visitor & VIP" },
                        { id: "CartonCountingPlugin", label: "Material Counting" },
                        { id: "RestrictionZonePlugin", label: "Restriction Zone" },
                      ].map((p) => {
                        const isSelected = selectedPlugins.includes(p.id)
                        return (
                          <button
                            type="button"
                            key={p.id}
                            onClick={() => togglePluginSelection(p.id)}
                            className={cn(
                              "text-xs px-2.5 py-2 rounded-lg border text-left font-medium transition-all flex items-center justify-between",
                              isSelected 
                                ? "bg-primary/20 border-primary text-primary shadow-sm" 
                                : "bg-background/60 border-border text-muted-foreground hover:text-foreground hover:border-foreground/20"
                            )}
                          >
                            <span className="truncate">{p.label}</span>
                            <span className={cn("w-2 h-2 rounded-full shrink-0 ml-1.5", isSelected ? "bg-primary glow-primary" : "bg-muted")} />
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  <button 
                    type="submit" 
                    disabled={isSubmitting}
                    className="w-full flex justify-center items-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors shadow-lg shadow-primary/20 disabled:opacity-50 disabled:cursor-not-allowed mt-4"
                  >
                    <Plus className="w-4 h-4" /> {isSubmitting ? 'Connecting...' : 'Add Camera Stream'}
                  </button>
                </form>

                <CameraStatusList />
              </div>
            </>
          )}


          {activeTab === 'People' && isAdmin && (
            <>
              <div className="flex items-center gap-2 mb-6 border-b border-border pb-4">
                <Users className="w-6 h-6 text-primary" />
                <h2 className="text-xl font-semibold">User & Roles Management</h2>
              </div>
              
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
                
                {/* Users List */}
                <div className="xl:col-span-2">
                  <h3 className="font-medium mb-4 flex items-center justify-between">
                    Active Operators
                    <button onClick={fetchUsers} className="text-xs text-primary hover:underline">Refresh</button>
                  </h3>
                  
                  {usersError && (
                    <div className="bg-danger/10 border border-danger/20 text-danger p-3 rounded-lg text-sm flex items-center gap-2 mb-4">
                      <ShieldAlert className="w-4 h-4 shrink-0" />
                      <span>{usersError}</span>
                    </div>
                  )}

                  <div className="bg-muted/10 border border-border rounded-xl overflow-hidden">
                    <table className="w-full text-sm text-left">
                      <thead className="bg-muted/30 text-muted-foreground text-xs uppercase">
                        <tr>
                          <th className="px-4 py-3 font-medium">User Email</th>
                          <th className="px-4 py-3 font-medium">Role</th>
                          <th className="px-4 py-3 font-medium">Status</th>
                          <th className="px-4 py-3 font-medium text-right">Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {usersLoading ? (
                          <tr><td colSpan={4} className="px-4 py-8 text-center text-muted-foreground"><Loader2 className="w-5 h-5 animate-spin mx-auto" /></td></tr>
                        ) : users.length === 0 ? (
                          <tr><td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">No users found.</td></tr>
                        ) : (
                          users.map((u) => (
                            <tr key={u.id} className="border-t border-border/50 hover:bg-muted/10 transition-colors">
                              <td className="px-4 py-3 font-medium text-foreground">{u.email}</td>
                              <td className="px-4 py-3">
                                {u.is_superuser ? (
                                  <span className="px-2 py-0.5 rounded-full bg-danger/20 text-danger text-xs">Superuser</span>
                                ) : (
                                  <select 
                                    className="bg-background border border-border rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-primary w-full max-w-[120px] capitalize"
                                    value={u.roles?.[0] || ''}
                                    onChange={async (e) => {
                                      const success = await assignRole(u.id, e.target.value);
                                      if (success) addToast({ title: 'Role Updated', message: `Updated role for ${u.email}`, type: 'success' });
                                    }}
                                  >
                                    <option value="" disabled>Select Role</option>
                                    {roles.map((r) => (
                                      <option key={r.id} value={r.name}>{r.name}</option>
                                    ))}
                                  </select>
                                )}
                              </td>
                              <td className="px-4 py-3">
                                {u.is_active ? (
                                  <span className="flex items-center gap-1.5 text-xs text-success"><div className="w-1.5 h-1.5 rounded-full bg-success"></div>Active</span>
                                ) : (
                                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><div className="w-1.5 h-1.5 rounded-full bg-muted-foreground"></div>Disabled</span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-right text-muted-foreground text-xs">{new Date(u.created_at).toLocaleDateString()}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Add User Form */}
                <div className="xl:col-span-1">
                  <div className="bg-muted/20 border border-border rounded-xl p-5">
                    <h3 className="font-medium mb-4 flex items-center gap-2">
                      <UserPlus className="w-4 h-4 text-primary" />
                      Invite Operator
                    </h3>
                    
                    <form onSubmit={async (e) => {
                      e.preventDefault();
                      const success = await createUser(newUserEmail, newUserPassword);
                      if (success) {
                        addToast({ title: 'User Created', message: `${newUserEmail} has been added.`, type: 'success' });
                        setNewUserEmail('');
                        setNewUserPassword('');
                      }
                    }} className="space-y-4">
                      
                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-muted-foreground">Email Address</label>
                        <input 
                          type="email" 
                          value={newUserEmail}
                          onChange={(e) => setNewUserEmail(e.target.value)}
                          placeholder="operator@devavision.ai" 
                          className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary w-full" 
                          required
                        />
                      </div>

                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-muted-foreground">Temporary Password</label>
                        <input 
                          type="password" 
                          value={newUserPassword}
                          onChange={(e) => setNewUserPassword(e.target.value)}
                          placeholder="••••••••" 
                          className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary w-full" 
                          required
                        />
                      </div>

                      <button 
                        type="submit" 
                        disabled={usersLoading}
                        className="w-full flex justify-center items-center gap-2 px-4 py-2 bg-primary/20 text-primary hover:bg-primary hover:text-white border border-primary/50 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed mt-2"
                      >
                        {usersLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Plus className="w-4 h-4" /> Create User</>}
                      </button>
                    </form>
                  </div>
                </div>
              </div>
            </>
          )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
