import React, { useMemo, useState } from 'react'
import { Building2, Plus, Trash2, Check, HardHat, TrendingUp } from 'lucide-react'
import { useProjectConfigStore } from '@/store/useProjectConfigStore'
import { useToastStore } from '@/store/useToastStore'

function formatTzLabel(tz: string): string {
  try {
    const now = new Date()
    const offset = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      timeZoneName: 'shortOffset',
    })
      .formatToParts(now)
      .find((p) => p.type === 'timeZoneName')?.value || ''

    return `${tz} (${offset})`
  } catch {
    return tz
  }
}

function getAllTimezones(): { value: string; label: string }[] {
  try {
    const zones: string[] = (Intl as any).supportedValuesOf('timeZone')
    return zones.map((tz) => ({ value: tz, label: formatTzLabel(tz) }))
  } catch {
    const fallback = [
      'UTC','America/New_York','America/Chicago','America/Denver','America/Los_Angeles',
      'Europe/London','Europe/Paris','Asia/Kolkata','Asia/Dubai','Asia/Singapore','Asia/Tokyo',
    ]
    return fallback.map((tz) => ({ value: tz, label: formatTzLabel(tz) }))
  }
}

export function OrganizationTab() {
  const timezones = useMemo(() => getAllTimezones(), [])
  const { addToast } = useToastStore()

  const {
    projectName,
    phaseName,
    overallProgress,
    timezone,
    milestones,
    setProjectConfig,
    addMilestone,
    updateMilestone,
    deleteMilestone,
  } = useProjectConfigStore()

  const [siteNameInput, setSiteNameInput] = useState(projectName)
  const [phaseInput, setPhaseInput] = useState(phaseName)
  const [overallInput, setOverallInput] = useState(overallProgress.toString())
  const [timezoneInput, setTimezoneInput] = useState(timezone || 'Asia/Kolkata')

  const [newLabel, setNewLabel] = useState('')
  const [newProgress, setNewProgress] = useState('50')

  const handleSaveProjectDetails = () => {
    setProjectConfig({
      projectName: siteNameInput,
      phaseName: phaseInput,
      overallProgress: parseFloat(overallInput) || 0,
      timezone: timezoneInput,
    })
    addToast({
      title: 'Project Settings Saved',
      message: 'Site phase, timezone & milestone targets updated on Dashboard!',
      type: 'success',
    })
  }

  const handleAddMilestone = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newLabel.trim()) return
    addMilestone(newLabel.trim(), parseInt(newProgress) || 0)
    setNewLabel('')
    setNewProgress('50')
    addToast({ title: 'Milestone Added', message: `Added "${newLabel}"`, type: 'success' })
  }

  return (
    <div className="relative z-10 space-y-8 max-w-2xl">
      <div className="flex items-center gap-3">
        <Building2 className="w-6 h-6 text-primary" />
        <div>
          <h2 className="text-xl font-bold text-blue-900 dark:text-white tracking-wide">Organization & Construction Project</h2>
          <p className="text-xs text-blue-700/80 dark:text-muted-foreground">Manage construction site details, current phase, and milestone progress.</p>
        </div>
      </div>

      {/* Basic Site Details */}
      <div className="bg-background/40 p-5 rounded-2xl border border-foreground/10 space-y-4">
        <h3 className="text-sm font-bold text-blue-900 dark:text-white uppercase tracking-wider flex items-center gap-2">
          <Building2 className="w-4 h-4 text-primary" /> General Site Info
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-blue-800 dark:text-muted-foreground uppercase">Site / Project Name</label>
            <input
              type="text"
              value={siteNameInput}
              onChange={(e) => setSiteNameInput(e.target.value)}
              className="bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-blue-900 dark:text-white focus:border-primary focus:outline-none"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-blue-800 dark:text-muted-foreground uppercase">Timezone</label>
            <select
              value={timezoneInput}
              onChange={(e) => setTimezoneInput(e.target.value)}
              className="bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-blue-900 dark:text-white focus:border-primary focus:outline-none"
            >
              {timezones.map((tz) => (
                <option key={tz.value} value={tz.value} className="bg-background text-blue-900 dark:text-white">
                  {tz.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Construction Site Phase & Milestones Manager */}
      <div className="bg-background/40 p-5 rounded-2xl border border-foreground/10 space-y-5">
        <div className="flex justify-between items-center border-b border-foreground/10 pb-3">
          <h3 className="text-sm font-bold text-blue-900 dark:text-white uppercase tracking-wider flex items-center gap-2">
            <HardHat className="w-4 h-4 text-warning" /> Project Milestones & Phase Config
          </h3>
          <span className="text-xs text-blue-700/80 dark:text-muted-foreground italic">Syncs directly to Dashboard</span>
        </div>

        {/* Phase Name & Overall Target */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2 flex flex-col gap-1.5">
            <label className="text-xs font-bold text-blue-800 dark:text-muted-foreground uppercase">Current Construction Phase</label>
            <input
              type="text"
              value={phaseInput}
              onChange={(e) => setPhaseInput(e.target.value)}
              placeholder="e.g. Phase 2 — Structural Shell"
              className="bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-blue-900 dark:text-white focus:border-primary focus:outline-none font-semibold"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-blue-800 dark:text-muted-foreground uppercase">Overall Target %</label>
            <div className="relative">
              <input
                type="number"
                min="0"
                max="100"
                value={overallInput}
                onChange={(e) => setOverallInput(e.target.value)}
                className="w-full bg-background/60 border border-foreground/10 rounded-xl px-4 py-2.5 text-sm text-blue-900 dark:text-white focus:border-primary focus:outline-none font-bold"
              />
              <TrendingUp className="w-4 h-4 text-primary absolute right-3 top-3 pointer-events-none" />
            </div>
          </div>
        </div>

        {/* Milestones List */}
        <div className="space-y-3">
          <label className="text-xs font-bold text-blue-800 dark:text-muted-foreground uppercase block">Active Structure / Floor Milestones</label>
          <div className="space-y-2">
            {milestones.map((m) => (
              <div key={m.id} className="p-3 rounded-xl bg-foreground/5 border border-foreground/10 flex items-center gap-3">
                <input
                  type="text"
                  value={m.label}
                  onChange={(e) => updateMilestone(m.id, e.target.value, m.progress, m.status)}
                  className="flex-1 bg-transparent border-b border-foreground/10 focus:border-primary px-1 py-1 text-xs text-blue-900 dark:text-white focus:outline-none"
                />
                <div className="flex items-center gap-2 w-32">
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={m.progress}
                    onChange={(e) => updateMilestone(m.id, m.label, parseInt(e.target.value) || 0, m.status)}
                    className="w-20 accent-primary cursor-pointer"
                  />
                  <span className="text-xs font-mono font-bold text-primary w-10 text-right">{m.progress}%</span>
                </div>
                <button
                  onClick={() => {
                    deleteMilestone(m.id)
                    addToast({ title: 'Milestone Deleted', message: `Removed "${m.label}"`, type: 'default' })
                  }}
                  className="p-1.5 rounded-lg hover:bg-danger/20 text-muted-foreground hover:text-danger transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          {/* Add New Milestone Form */}
          <form onSubmit={handleAddMilestone} className="flex gap-2 pt-2">
            <input
              type="text"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              placeholder="Add new milestone (e.g. Tower C - Column Rebar)..."
              className="flex-1 bg-background/60 border border-foreground/10 rounded-xl px-3 py-2 text-xs text-blue-900 dark:text-white focus:outline-none focus:border-primary"
            />
            <input
              type="number"
              min="0"
              max="100"
              value={newProgress}
              onChange={(e) => setNewProgress(e.target.value)}
              className="w-16 bg-background/60 border border-foreground/10 rounded-xl px-2 py-2 text-xs text-blue-900 dark:text-white text-center focus:outline-none focus:border-primary font-bold"
            />
            <button
              type="submit"
              className="px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-1 shrink-0"
            >
              <Plus className="w-4 h-4" /> Add
            </button>
          </form>
        </div>

        {/* Save Button */}
        <div className="pt-2 flex justify-end">
          <button
            onClick={handleSaveProjectDetails}
            className="px-5 py-2.5 bg-primary hover:bg-primary/90 text-white rounded-xl text-xs font-bold transition-all shadow-md flex items-center gap-2"
          >
            <Check className="w-4 h-4" /> Save Project Configuration
          </button>
        </div>
      </div>
    </div>
  )
}
