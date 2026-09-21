import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, CheckCircle, Info, XCircle, X, Camera } from 'lucide-react'
import { useToastStore } from '@/store/useToastStore'
import { cn } from '@/utils/utils'

const icons = {
  default: Info,
  success: CheckCircle,
  warning: AlertCircle,
  danger: XCircle,
}

const styles = {
  default: 'bg-card border-border text-foreground',
  success: 'bg-success/10 border-success/30 text-success-foreground',
  warning: 'bg-warning/10 border-warning/30 text-warning-foreground',
  danger: 'bg-danger/10 border-danger/30 text-danger-foreground',
}

const iconStyles = {
  default: 'text-primary',
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
}

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore()

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      <AnimatePresence>
        {toasts.map((toast) => {
          const Icon = icons[toast.type || 'default']
          return (
            <motion.div
              key={toast.id}
              initial={{ opacity: 0, y: 50, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.2 } }}
              className={cn(
                'pointer-events-auto flex gap-3 p-4 rounded-xl border shadow-xl backdrop-blur-md relative overflow-hidden',
                styles[toast.type || 'default']
              )}
            >
              {/* Highlight bar */}
              <div className={cn("absolute left-0 top-0 bottom-0 w-1 bg-current opacity-50", iconStyles[toast.type || 'default'])} />
              
              <div className="shrink-0 pt-0.5">
                <Icon className={cn('w-5 h-5', iconStyles[toast.type || 'default'])} />
              </div>
              
              <div className="flex flex-col flex-1 gap-1 min-w-0">
                <p className="text-sm font-semibold leading-none text-foreground">{toast.title}</p>
                <p className="text-sm opacity-90 leading-tight">{toast.message}</p>
                
                {toast.cameraName && (
                  <div className="flex items-center gap-1.5 mt-1.5 text-xs font-medium text-muted-foreground bg-background/20 self-start px-2 py-0.5 rounded-md">
                    <Camera className="w-3 h-3" />
                    <span className="truncate">{toast.cameraName}</span>
                  </div>
                )}
              </div>

              <button
                onClick={() => removeToast(toast.id)}
                className="shrink-0 opacity-50 hover:opacity-100 transition-opacity p-1 -mr-2 -mt-2 self-start rounded-md hover:bg-background/10"
              >
                <X className="w-4 h-4 text-foreground" />
              </button>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
