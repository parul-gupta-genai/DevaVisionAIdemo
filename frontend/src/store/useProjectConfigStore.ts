import { create } from 'zustand'

export interface Milestone {
  id: string
  label: string
  progress: number
  status: string
}

export interface ProjectConfig {
  projectName: string
  phaseName: string
  overallProgress: number
  timezone: string
  milestones: Milestone[]
}

const DEFAULT_CONFIG: ProjectConfig = {
  projectName: 'Hero Homes NCR - Sector 42',
  phaseName: 'Phase 2 — Structural Shell',
  overallProgress: 88.5,
  timezone: 'Asia/Kolkata',
  milestones: [
    { id: 'm1', label: 'Tower A - 5th Floor Slab', progress: 92, status: 'Near Completion' },
    { id: 'm2', label: 'Tower B - Column Rebar', progress: 68, status: 'In Progress' },
    { id: 'm3', label: 'Basement Parking Wiring', progress: 45, status: 'On Schedule' },
  ],
}

function loadInitialConfig(): ProjectConfig {
  try {
    const saved = localStorage.getItem('devavision_project_config')
    if (saved) {
      const parsed = JSON.parse(saved)
      return { ...DEFAULT_CONFIG, ...parsed }
    }
  } catch (e) {}
  return DEFAULT_CONFIG
}

interface ProjectConfigStore extends ProjectConfig {
  setProjectConfig: (config: Partial<ProjectConfig>) => void
  addMilestone: (label: string, progress: number, status?: string) => void
  updateMilestone: (id: string, label: string, progress: number, status?: string) => void
  deleteMilestone: (id: string) => void
}

export const useProjectConfigStore = create<ProjectConfigStore>((set, get) => {
  const initial = loadInitialConfig()

  return {
    ...initial,
    setProjectConfig: (newConfig) => {
      set((state) => {
        const updated = { ...state, ...newConfig }
        const toSave = {
          projectName: updated.projectName,
          phaseName: updated.phaseName,
          overallProgress: updated.overallProgress,
          timezone: updated.timezone || 'Asia/Kolkata',
          milestones: updated.milestones,
        }
        localStorage.setItem('devavision_project_config', JSON.stringify(toSave))
        return updated
      })
    },
    addMilestone: (label, progress, status = 'In Progress') => {
      const newM: Milestone = {
        id: Math.random().toString(36).substring(2, 9),
        label,
        progress,
        status,
      }
      get().setProjectConfig({ milestones: [...get().milestones, newM] })
    },
    updateMilestone: (id, label, progress, status = 'In Progress') => {
      const updated = get().milestones.map((m) =>
        m.id === id ? { ...m, label, progress, status } : m
      )
      get().setProjectConfig({ milestones: updated })
    },
    deleteMilestone: (id) => {
      const filtered = get().milestones.filter((m) => m.id !== id)
      get().setProjectConfig({ milestones: filtered })
    },
  }
})
