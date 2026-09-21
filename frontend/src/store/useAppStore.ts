import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'dark' | 'light' | 'colorful'

interface AppState {
  sidebarOpen: boolean
  toggleSidebar: () => void
  rightPanelOpen: boolean
  toggleRightPanel: () => void
  activeCameraId: string | null
  setActiveCamera: (id: string | null) => void
  theme: Theme
  cycleTheme: () => void
  toggleTheme: () => void
  isAIChatOpen: boolean
  toggleAIChat: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      rightPanelOpen: false,
      toggleRightPanel: () => set((state) => ({ rightPanelOpen: !state.rightPanelOpen })),
      isAIChatOpen: false,
      toggleAIChat: () => set((state) => ({ isAIChatOpen: !state.isAIChatOpen })),
      activeCameraId: null,
      setActiveCamera: (id) => set({ activeCameraId: id }),
      theme: 'light',
      cycleTheme: () => set((state) => {
        const themes: Theme[] = ['dark', 'light', 'colorful'];
        const currentIndex = themes.indexOf(state.theme);
        const nextIndex = (currentIndex + 1) % themes.length;
        return { theme: themes[nextIndex] };
      }),
      toggleTheme: () => set((state) => {
        const isDark = state.theme === 'dark';
        const newTheme: Theme = isDark ? 'light' : 'dark';
        // Update html class for Tailwind dark mode
        if (newTheme === 'dark') document.documentElement.classList.add('dark');
        else document.documentElement.classList.remove('dark');
        return { theme: newTheme };
      }),
    }),
    {
      name: 'devavisionai-app-storage',
      partialize: (state) => ({ theme: state.theme }), // Only persist the theme
    }
  )
)
