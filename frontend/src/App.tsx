

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from './layouts/Layout'
import { Dashboard } from './pages/Dashboard'
import { LiveCameras } from './pages/LiveCameras'
import { Analytics, Events } from './pages/EventsAndAnalytics'

import Vehicles from './pages/Vehicles';
import Attendance from './pages/Attendance'
import { FaceWatchlist } from './pages/FaceWatchlist'
import { RestrictedZones } from './pages/RestrictedZones'
import { FireAnalytics } from './pages/FireAnalytics'
import Materials from './pages/Materials';
import PPEAnalytics from './pages/PPEAnalytics';
import Visitors from './pages/Visitors';
import EmployeeDirectory from './pages/EmployeeDirectory';
import VisitorRegistration from './pages/VisitorRegistration';
import { Settings } from './pages/Settings'
import { ProviderPortal } from './pages/ProviderPortal'
import { Login } from './pages/Login'
import { AuthProvider } from './contexts/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'

import { useEffect } from 'react'
import { useCameraStateStore } from './store/useCameraStateStore'
import { useAppStore } from './store/useAppStore'
import { useAuth } from './contexts/AuthContext'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      gcTime: 1000 * 60 * 30, // 30 minutes
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})


import React, { Component } from 'react';

class ErrorBoundary extends Component<any, any> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: any) {
    return { hasError: true, error };
  }

  componentDidCatch(error: any, errorInfo: any) {
    this.setState({ errorInfo });
    console.error(error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "20px", color: "white", backgroundColor: "black", height: "100vh", overflow: "auto" }}>
          <h1 style={{ color: "red" }}>Oops, React crashed!</h1>
          <p>Please take a screenshot of this error and send it to the agent:</p>
          <pre style={{ color: "lime", backgroundColor: "#222", padding: "10px" }}>
            {this.state.error?.toString()}
          </pre>
          <pre style={{ color: "pink", backgroundColor: "#222", padding: "10px" }}>
            {this.state.errorInfo?.componentStack}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

function AppInner() {
  const connect = useCameraStateStore(state => state.connect)
  const disconnect = useCameraStateStore(state => state.disconnect)
  const theme = useAppStore(state => state.theme)
  const { isAuthenticated, isLoading } = useAuth()

  // Only connect WebSocket after the user is authenticated.
  // Connecting before login sends an empty token → backend returns 403.
  useEffect(() => {
    if (!isAuthenticated || isLoading) return
    connect()
    return () => disconnect()
  }, [isAuthenticated, isLoading])

  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<VisitorRegistration />} />
          <Route path="/provider" element={<ProviderPortal />} />

          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="cameras" element={<LiveCameras />} />
              <Route path="events" element={<Events />} />
              <Route path="analytics" element={<Analytics />} />

              <Route path="attendance" element={<Attendance />} />
              <Route path="face-watchlist" element={<FaceWatchlist />} />
              <Route path="fire" element={<FireAnalytics />} />
              <Route path="materials" element={<Materials />} />
              <Route path="ppe" element={<PPEAnalytics />} />
              <Route path="restricted-zones" element={<RestrictedZones />} />

              <Route path="vehicles" element={<Vehicles />} />
              <Route path="visitors" element={<Visitors />} />
              <Route path="employee-db" element={<EmployeeDirectory />} />

              <Route path="settings" element={<Settings />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster theme={theme === 'colorful' ? 'light' : theme} position="bottom-right" />
    </ErrorBoundary>
  )
}

// AppInner must live inside AuthProvider to access useAuth().
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AppInner />
      </AuthProvider>
    </QueryClientProvider>
  )
}

export default App
