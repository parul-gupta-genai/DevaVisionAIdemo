import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../api/api';
import { ShieldAlert, Loader2, Eye, EyeOff, Sun, Moon } from 'lucide-react';

export const Login: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem('login-theme');
    if (saved) return saved === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/';

  useEffect(() => {
    localStorage.setItem('login-theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);

    try {
      const response = await api.post('/auth/login', { email, password });
      await login(response.data.access_token, response.data.refresh_token);
      navigate(from, { replace: true });
    } catch (err: any) {
      if (err.response?.status === 401) {
        setError('Invalid email or password.');
      } else if (err.response?.status === 403) {
        setError('Account locked due to multiple failed attempts. Try again later.');
      } else if (err.response?.status === 429) {
        setError('Too many login attempts. Please wait a moment and try again.');
      } else if (!err.response) {
        setError('Cannot reach the backend server. Please verify the API is running on port 8000.');
      } else {
        setError(err.response?.data?.detail || 'An unexpected error occurred. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden transition-colors duration-500"
      style={{
        background: isDark
          ? 'linear-gradient(135deg, #0a0a0a 0%, #0d1117 40%, #010409 100%)'
          : 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 40%, #f1f5f9 100%)',
      }}
    >
      {/* Ambient glow orbs */}
      <div
        className="absolute top-[-15%] left-[-10%] w-[50%] h-[50%] rounded-full pointer-events-none animate-pulse"
        style={{
          background: isDark
            ? 'radial-gradient(circle, rgba(59,130,246,0.12) 0%, transparent 70%)'
            : 'radial-gradient(circle, rgba(59,130,246,0.08) 0%, transparent 70%)',
          filter: 'blur(80px)',
        }}
      />
      <div
        className="absolute bottom-[-15%] right-[-10%] w-[50%] h-[50%] rounded-full pointer-events-none animate-pulse"
        style={{
          background: isDark
            ? 'radial-gradient(circle, rgba(139,92,246,0.12) 0%, transparent 70%)'
            : 'radial-gradient(circle, rgba(139,92,246,0.06) 0%, transparent 70%)',
          filter: 'blur(80px)',
          animationDelay: '2s',
        }}
      />

      {/* Subtle grid overlay (dark mode only) */}
      {isDark && (
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.03]"
          style={{
            backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px),
                              linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
            backgroundSize: '40px 40px',
          }}
        />
      )}

      {/* Theme toggle */}
      <button
        onClick={() => setIsDark(!isDark)}
        className="absolute top-6 right-6 z-20 p-2.5 rounded-xl transition-all duration-300 group"
        style={{
          background: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)',
          border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'}`,
        }}
        aria-label="Toggle theme"
      >
        {isDark ? (
          <Sun className="w-5 h-5 transition-transform duration-300 group-hover:rotate-45" style={{ color: '#fbbf24' }} />
        ) : (
          <Moon className="w-5 h-5 transition-transform duration-300 group-hover:-rotate-12" style={{ color: '#6366f1' }} />
        )}
      </button>

      <div className="w-full max-w-[420px] relative z-10">
        {/* Main card */}
        <div
          className="rounded-3xl p-8 sm:p-10 transition-all duration-500"
          style={{
            background: isDark
              ? 'rgba(15,15,20,0.85)'
              : 'rgba(255,255,255,0.8)',
            backdropFilter: 'blur(40px) saturate(180%)',
            border: `1px solid ${isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'}`,
            boxShadow: isDark
              ? '0 25px 60px -12px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.03) inset'
              : '0 25px 60px -12px rgba(0,0,0,0.1), 0 0 0 1px rgba(255,255,255,0.8) inset',
          }}
        >
          {/* Logo & branding */}
          <div className="flex flex-col items-center mb-8">
            <div
              className="w-20 h-20 rounded-2xl flex items-center justify-center mb-5 overflow-hidden"
              style={{
                background: isDark
                  ? 'linear-gradient(135deg, rgba(59,130,246,0.15), rgba(139,92,246,0.15))'
                  : 'linear-gradient(135deg, rgba(59,130,246,0.1), rgba(139,92,246,0.1))',
                border: `1px solid ${isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)'}`,
              }}
            >
              <img
                src="/Hero_Homes.png"
                alt="Hero Homes"
                className="w-16 h-16 object-contain rounded-xl"
              />
            </div>

            <h1
              className="text-2xl font-bold tracking-wide uppercase"
              style={{
                background: 'linear-gradient(135deg, #3b82f6, #8b5cf6, #ec4899)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
              }}
            >
              Hero Homes
            </h1>
            <p
              className="mt-2 text-center text-sm font-medium tracking-wide"
              style={{ color: isDark ? '#71717a' : '#a1a1aa' }}
            >
              Enterprise AI Surveillance Platform
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Error alert */}
            {error && (
              <div
                className="flex items-center gap-2.5 p-3.5 rounded-xl text-sm font-medium"
                style={{
                  background: isDark ? 'rgba(239,68,68,0.08)' : 'rgba(239,68,68,0.06)',
                  border: `1px solid ${isDark ? 'rgba(239,68,68,0.15)' : 'rgba(239,68,68,0.12)'}`,
                  color: isDark ? '#f87171' : '#dc2626',
                }}
              >
                <ShieldAlert className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Email field */}
            <div>
              <label
                className="block text-xs font-semibold uppercase tracking-wider mb-2"
                htmlFor="email"
                style={{ color: isDark ? '#a1a1aa' : '#71717a' }}
              >
                Email Address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl px-4 py-3 text-sm transition-all duration-200 outline-none"
                style={{
                  background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
                  border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'}`,
                  color: isDark ? '#f4f4f5' : '#18181b',
                }}
                onFocus={(e) => {
                  e.target.style.borderColor = '#3b82f6';
                  e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.15)';
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
                  e.target.style.boxShadow = 'none';
                }}
                placeholder="you@company.com"
                required
              />
            </div>

            {/* Password field */}
            <div>
              <label
                className="block text-xs font-semibold uppercase tracking-wider mb-2"
                htmlFor="password"
                style={{ color: isDark ? '#a1a1aa' : '#71717a' }}
              >
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-xl px-4 py-3 pr-12 text-sm transition-all duration-200 outline-none"
                  style={{
                    background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
                    border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'}`,
                    color: isDark ? '#f4f4f5' : '#18181b',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = '#3b82f6';
                    e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.15)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
                    e.target.style.boxShadow = 'none';
                  }}
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-lg transition-colors duration-200"
                  style={{ color: isDark ? '#71717a' : '#a1a1aa' }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = isDark ? '#d4d4d8' : '#52525b'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = isDark ? '#71717a' : '#a1a1aa'; }}
                >
                  {showPassword ? <EyeOff className="w-4.5 h-4.5" /> : <Eye className="w-4.5 h-4.5" />}
                </button>
              </div>
            </div>

            {/* Submit button */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full font-semibold rounded-xl px-4 py-3.5 text-sm transition-all duration-300 flex items-center justify-center mt-2 disabled:opacity-60 disabled:cursor-not-allowed group relative overflow-hidden"
              style={{
                background: 'linear-gradient(135deg, #3b82f6, #6366f1, #8b5cf6)',
                color: '#ffffff',
                boxShadow: '0 8px 24px -4px rgba(99,102,241,0.35)',
              }}
              onMouseEnter={(e) => {
                if (!isSubmitting) {
                  e.currentTarget.style.boxShadow = '0 12px 32px -4px rgba(99,102,241,0.5)';
                  e.currentTarget.style.transform = 'translateY(-1px)';
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.boxShadow = '0 8px 24px -4px rgba(99,102,241,0.35)';
                e.currentTarget.style.transform = 'translateY(0)';
              }}
            >
              {/* Shimmer effect */}
              <div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                style={{
                  background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent)',
                  animation: 'shimmer 2s infinite',
                }}
              />
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  Authenticating...
                </>
              ) : (
                'Sign In to Dashboard'
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p
          className="text-center text-xs mt-6 font-medium"
          style={{ color: isDark ? '#3f3f46' : '#d4d4d8' }}
        >
          &copy; {new Date().getFullYear()} DevaVision AI &middot; Secured with enterprise-grade encryption
        </p>
      </div>

      {/* Shimmer keyframes */}
      <style>{`
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
      `}</style>
    </div>
  );
};
