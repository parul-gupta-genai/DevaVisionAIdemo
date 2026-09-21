import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

interface ProtectedRouteProps {
  requireRoles?: string[];
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ requireRoles }) => {
  const { isAuthenticated, isLoading, user } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-950">
        <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (requireRoles && requireRoles.length > 0) {
    const hasRole = user.roles.some((role) => requireRoles.includes(role));
    if (!hasRole && !user.is_superuser) {
      return (
        <div className="flex flex-col items-center justify-center min-h-screen bg-slate-950 text-slate-200">
          <h1 className="text-3xl font-bold text-red-500 mb-4">403 - Forbidden</h1>
          <p>You do not have permission to view this page.</p>
        </div>
      );
    }
  }

  return <Outlet />;
};
