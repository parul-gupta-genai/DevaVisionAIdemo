import { Outlet } from 'react-router-dom'
import { TopNav } from './TopNav'
import { Sidebar } from './Sidebar'
import { RightPanel } from './RightPanel'
import { useAppStore } from '@/store/useAppStore'
import { useEffect } from 'react'
import { ToastContainer } from '../components/ui/ToastContainer'
import AIChatWidget from '../components/AIChat/AIChatWidget'

export function Layout() {
  const { theme } = useAppStore()

  useEffect(() => {
    document.documentElement.classList.remove('dark', 'theme-colorful')
    
    if (theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else if (theme === 'colorful') {
      document.documentElement.classList.add('theme-colorful')
    }
  }, [theme])

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground transition-colors duration-300 relative">
      <TopNav />
      <div className="flex flex-1 overflow-hidden relative z-10">
        <Sidebar />
        <main className="flex-1 overflow-auto bg-transparent relative z-0">
          <Outlet />
        </main>
        <RightPanel />
      </div>
      <AIChatWidget />
      <ToastContainer />
    </div>
  )
}
