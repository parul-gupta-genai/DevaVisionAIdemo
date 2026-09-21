import React, { useState } from 'react'
import { Loader2, BrainCircuit, Key, Sparkles, Cpu, Globe, Server, Check, Eye, EyeOff, Info } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/utils/utils'

const LLM_PROVIDERS = [
  {
    id: 'groq',
    name: 'Groq Cloud',
    badge: 'Recommended · Free',
    icon: Sparkles,
    desc: 'Ultra-fast cloud inference with Llama 3. Free API key available at console.groq.com.',
    models: [
      { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B (Versatile - Smartest)' },
      { id: 'llama-3.1-8b-instant', name: 'Llama 3.1 8B (Instant - Fastest)' },
      { id: 'mixtral-8x7b-32768', name: 'Mixtral 8x7B (Large Context)' },
      { id: 'gemma2-9b-it', name: 'Gemma 2 9B (Google)' },
    ],
  },
  {
    id: 'ollama',
    name: 'Ollama Local',
    badge: '100% Offline · Jetson',
    icon: Cpu,
    desc: 'Runs completely offline on your Jetson or local PC. No API key required.',
    models: [
      { id: 'llama3.2:3b', name: 'Llama 3.2 3B (Fast & Lightweight for Jetson)' },
      { id: 'qwen2.5:7b', name: 'Qwen 2.5 7B (Best Hindi & Multilingual)' },
      { id: 'mistral:7b', name: 'Mistral 7B (Balanced)' },
      { id: 'phi3:mini', name: 'Phi-3 Mini 3.8B (Microsoft)' },
      { id: 'llama3.1:8b', name: 'Llama 3.1 8B' },
    ],
  },
  {
    id: 'openai',
    name: 'OpenAI',
    badge: 'Cloud API',
    icon: Globe,
    desc: 'GPT-4o models with high reasoning and structured data extraction.',
    models: [
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini (Fast & Cost Efficient)' },
      { id: 'gpt-4o', name: 'GPT-4o (Most Accurate)' },
    ],
  },
]

export function AIConfigTab({ backendConfig, setBackendConfig, configLoading }: any) {
  const [showGroqKey, setShowGroqKey] = useState(false)
  const [showOpenAIKey, setShowOpenAIKey] = useState(false)

  if (configLoading) {
    return <div className="flex justify-center p-12"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>
  }

  const currentProvider = backendConfig.LLM_PROVIDER || 'groq'
  const activeProviderObj = LLM_PROVIDERS.find(p => p.id === currentProvider) || LLM_PROVIDERS[0]

  return (
    <div className="relative z-10 space-y-10">
      {/* ─── Header ────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center border border-primary/20">
          <BrainCircuit className="w-6 h-6 text-primary" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide">AI & LLM Configuration</h2>
          <p className="text-sm text-muted-foreground">Configure AI vision detection thresholds and Assistant LLM Brain</p>
        </div>
      </div>

      {/* ─── Section 1: LLM Brain & Reasoning Engine ───────── */}
      <div className="p-6 rounded-2xl bg-card/40 border border-border space-y-6">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            AI Assistant Brain (LLM Provider)
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Choose the language model that powers the AI Assistant, CCTV questions, and natural language analytics.
          </p>
        </div>

        {/* Provider Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {LLM_PROVIDERS.map((provider) => {
            const Icon = provider.icon
            const isSelected = currentProvider === provider.id
            return (
              <button
                key={provider.id}
                type="button"
                onClick={() => setBackendConfig({ ...backendConfig, LLM_PROVIDER: provider.id })}
                className={cn(
                  'p-4 rounded-xl text-left transition-all border relative flex flex-col justify-between gap-3',
                  isSelected
                    ? 'border-primary bg-primary/10 shadow-lg glow-primary/20'
                    : 'border-border bg-background/50 hover:border-foreground/20 hover:bg-muted/30'
                )}
              >
                <div className="flex items-start justify-between w-full">
                  <div className="flex items-center gap-2.5">
                    <div className={cn('p-2 rounded-lg', isSelected ? 'bg-primary text-white' : 'bg-muted text-muted-foreground')}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="font-semibold text-sm text-foreground">{provider.name}</div>
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-primary/20 text-primary">
                        {provider.badge}
                      </span>
                    </div>
                  </div>
                  {isSelected && <Check className="w-4 h-4 text-primary" />}
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">{provider.desc}</p>
              </button>
            )
          })}
        </div>

        {/* Dynamic Provider Settings */}
        <div className="space-y-4 pt-4 border-t border-border/50">
          {/* Model Selection */}
          <div className="flex flex-col gap-2 max-w-xl">
            <label className="text-xs font-bold tracking-widest uppercase text-muted-foreground">
              Selected AI Model ({activeProviderObj.name})
            </label>
            <select
              value={
                currentProvider === 'groq'
                  ? backendConfig.GROQ_MODEL || 'llama-3.3-70b-versatile'
                  : currentProvider === 'ollama'
                  ? backendConfig.OLLAMA_MODEL || 'llama3.2:3b'
                  : backendConfig.OPENAI_MODEL || 'gpt-4o-mini'
              }
              onChange={(e) => {
                const val = e.target.value
                if (currentProvider === 'groq') setBackendConfig({ ...backendConfig, GROQ_MODEL: val })
                else if (currentProvider === 'ollama') setBackendConfig({ ...backendConfig, OLLAMA_MODEL: val })
                else setBackendConfig({ ...backendConfig, OPENAI_MODEL: val })
              }}
              className="bg-background border border-border rounded-xl px-4 py-3 text-sm text-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-inner"
            >
              {activeProviderObj.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.id})
                </option>
              ))}
            </select>
          </div>

          {/* Groq API Key Input */}
          {currentProvider === 'groq' && (
            <div className="flex flex-col gap-2 max-w-xl">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold tracking-widest uppercase text-muted-foreground flex items-center gap-1.5">
                  <Key className="w-3.5 h-3.5 text-primary" /> Groq API Key
                </label>
                <a
                  href="https://console.groq.com/keys"
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-primary hover:underline flex items-center gap-1"
                >
                  Get free key at console.groq.com ↗
                </a>
              </div>
              <div className="relative">
                <input
                  type={showGroqKey ? 'text' : 'password'}
                  value={backendConfig.GROQ_API_KEY || ''}
                  onChange={(e) => setBackendConfig({ ...backendConfig, GROQ_API_KEY: e.target.value })}
                  placeholder="gsk_xxxxxxxxxxxxxxxxxxxxxxxx"
                  className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm font-mono text-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-inner pr-20"
                />
                <button
                  type="button"
                  onClick={() => setShowGroqKey(!showGroqKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded bg-muted/50 flex items-center gap-1"
                >
                  {showGroqKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  {showGroqKey ? 'Hide' : 'Show'}
                </button>
              </div>
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Info className="w-3.5 h-3.5 text-primary" /> Key is encrypted & saved to backend for AI assistant operations.
              </p>
            </div>
          )}

          {/* Ollama Base URL Input */}
          {currentProvider === 'ollama' && (
            <div className="flex flex-col gap-2 max-w-xl">
              <label className="text-xs font-bold tracking-widest uppercase text-muted-foreground flex items-center gap-1.5">
                <Server className="w-3.5 h-3.5 text-primary" /> Ollama Base URL
              </label>
              <input
                type="text"
                value={backendConfig.OLLAMA_BASE_URL || 'http://localhost:11434'}
                onChange={(e) => setBackendConfig({ ...backendConfig, OLLAMA_BASE_URL: e.target.value })}
                placeholder="http://localhost:11434"
                className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm font-mono text-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-inner"
              />
              <p className="text-xs text-muted-foreground">
                Run <code className="px-1.5 py-0.5 rounded bg-muted font-mono text-[11px]">ollama run {backendConfig.OLLAMA_MODEL || 'llama3.2:3b'}</code> locally on your PC or Jetson. No internet or API key required.
              </p>
            </div>
          )}

          {/* OpenAI API Key Input */}
          {currentProvider === 'openai' && (
            <div className="flex flex-col gap-2 max-w-xl">
              <label className="text-xs font-bold tracking-widest uppercase text-muted-foreground flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-primary" /> OpenAI API Key
              </label>
              <div className="relative">
                <input
                  type={showOpenAIKey ? 'text' : 'password'}
                  value={backendConfig.OPENAI_API_KEY || ''}
                  onChange={(e) => setBackendConfig({ ...backendConfig, OPENAI_API_KEY: e.target.value })}
                  placeholder="sk-proj-xxxxxxxxxxxxxxxxxxxx"
                  className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm font-mono text-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-inner pr-20"
                />
                <button
                  type="button"
                  onClick={() => setShowOpenAIKey(!showOpenAIKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded bg-muted/50 flex items-center gap-1"
                >
                  {showOpenAIKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  {showOpenAIKey ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ─── Section 2: Vision & Detection Pipeline ───────── */}
      <div className="p-6 rounded-2xl bg-card/40 border border-border space-y-6">
        <div>
          <h3 className="text-base font-semibold text-foreground">Computer Vision & Detection Policies</h3>
          <p className="text-xs text-muted-foreground mt-1">DeepStream YOLO object detection & tracking parameters</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="flex flex-col gap-2">
            <label className="text-xs font-bold tracking-widest uppercase text-muted-foreground">
              Confidence Threshold (0.0 - 1.0)
            </label>
            <input
              type="number"
              step="0.05"
              min="0.1"
              max="1.0"
              value={backendConfig.CONFIDENCE_THRESHOLD || 0.4}
              onChange={(e) => setBackendConfig({ ...backendConfig, CONFIDENCE_THRESHOLD: parseFloat(e.target.value) })}
              className="bg-background text-foreground border border-border rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-inner"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-xs font-bold tracking-widest uppercase text-muted-foreground">
              Loitering Threshold (Seconds)
            </label>
            <input
              type="number"
              min="1"
              max="300"
              value={backendConfig.LOITERING_THRESHOLD_SECONDS || 10}
              onChange={(e) => setBackendConfig({ ...backendConfig, LOITERING_THRESHOLD_SECONDS: parseFloat(e.target.value) })}
              className="bg-background text-foreground border border-border rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-inner"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-xs font-bold tracking-widest uppercase text-muted-foreground">
              Frame Skip (1 in X frames)
            </label>
            <input
              type="number"
              min="1"
              max="30"
              value={backendConfig.FRAME_SKIP || 3}
              onChange={(e) => setBackendConfig({ ...backendConfig, FRAME_SKIP: parseInt(e.target.value) })}
              className="bg-background text-foreground border border-border rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-inner"
            />
          </div>
        </div>

        <div className="flex items-center gap-4 py-4 border-t border-border/50">
          <div className="flex-1">
            <h4 className="font-semibold text-foreground text-sm">Enable Gesture Detection</h4>
            <p className="text-xs text-muted-foreground">Turn on hand & pose gesture tracking across live feeds.</p>
          </div>
          <div
            onClick={() => setBackendConfig({ ...backendConfig, GESTURE_ENABLED: !backendConfig.GESTURE_ENABLED })}
            className={`w-14 h-7 rounded-full relative cursor-pointer shadow-inner transition-colors duration-300 ${
              backendConfig.GESTURE_ENABLED ? 'bg-primary' : 'bg-muted border border-border'
            }`}
          >
            <motion.div
              layout
              className="absolute top-1 w-5 h-5 bg-white rounded-full shadow-md"
              initial={false}
              animate={{ x: backendConfig.GESTURE_ENABLED ? 26 : 4 }}
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
