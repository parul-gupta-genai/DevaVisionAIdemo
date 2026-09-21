import { HardHat, Hammer, TrendingUp, Building2 } from 'lucide-react'
import { useProjectConfigStore } from '@/store/useProjectConfigStore'

export function ConstructionProgressWidget() {
  const { phaseName, overallProgress, milestones } = useProjectConfigStore()

  return (
    <div className="glass-pro p-5 rounded-2xl flex flex-col justify-between border border-foreground/10 hover:border-primary/30 transition-all duration-300">
      <div className="flex justify-between items-center mb-3">
        <div className="flex items-center gap-2">
          <Building2 className="w-5 h-5 text-primary" />
          <div>
            <h4 className="text-xs font-bold tracking-widest uppercase text-muted-foreground">Site Progress & Operations</h4>
            <p className="text-sm font-bold text-foreground">{phaseName}</p>
          </div>
        </div>
        <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-primary/15 text-primary border border-primary/30 flex items-center gap-1">
          <TrendingUp className="w-3.5 h-3.5" /> {overallProgress}% On Track
        </span>
      </div>

      {/* Progress Bars */}
      <div className="space-y-3 my-2">
        {milestones.length === 0 ? (
          <div className="text-xs text-muted-foreground italic py-2 text-center">No active milestones configured.</div>
        ) : (
          milestones.map((m) => (
            <div key={m.id || m.label} className="space-y-1">
              <div className="flex justify-between text-xs font-medium">
                <span className="text-foreground truncate max-w-[200px]">{m.label}</span>
                <span className="text-muted-foreground">{m.progress}%</span>
              </div>
              <div className="w-full bg-foreground/10 h-2 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-primary to-accent transition-all duration-500 rounded-full"
                  style={{ width: `${m.progress}%` }}
                ></div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Bottom KPI badges */}
      <div className="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-foreground/5 text-xs">
        <div className="flex items-center justify-between p-2 rounded-xl bg-success/10 border border-success/20">
          <span className="text-muted-foreground font-medium flex items-center gap-1">
            <HardHat className="w-3.5 h-3.5 text-success" /> PPE Safety Score
          </span>
          <span className="font-extrabold text-success">96.4%</span>
        </div>
        <div className="flex items-center justify-between p-2 rounded-xl bg-info/10 border border-info/20">
          <span className="text-muted-foreground font-medium flex items-center gap-1">
            <Hammer className="w-3.5 h-3.5 text-info" /> Active Trades
          </span>
          <span className="font-extrabold text-info">54 Workers</span>
        </div>
      </div>
    </div>
  )
}
