import { useState, useEffect } from 'react'
import { Mic, Volume2, Zap, Globe, Key, CheckCircle, AlertCircle, Info, ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import { cn } from '@/utils/utils'
import { api } from '../../../api/api'
import { useToastStore } from '@/store/useToastStore'

// ─── Types ────────────────────────────────────────────────────────────────────

interface VoiceSettings {
  sttEngine: string
  ttsEngine: string
  language: string
  voiceGender: 'all' | 'female' | 'male'
  speechSpeed: number
  speechPitch: number
  speechVolume: number
  vadSensitivity: number
  groqApiKey: string
  openaiApiKey: string
  elevenLabsApiKey: string
  elevenLabsVoiceId: string
  rivaServerUrl: string
  kokoroModel: string
  kokoroVoice: string
  rivaVoice: string
  browserVoice: string
  enableVAD: boolean
  maxSilenceMs: number
}

// ─── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_SETTINGS: VoiceSettings = {
  sttEngine: 'browser',
  ttsEngine: 'browser',
  language: 'hi-IN',
  voiceGender: 'female',
  speechSpeed: 1.0,
  speechPitch: 1.0,
  speechVolume: 1.0,
  vadSensitivity: 0.5,
  groqApiKey: '',
  openaiApiKey: '',
  elevenLabsApiKey: '',
  elevenLabsVoiceId: '21m00Tcm4TlvDq8ikWAM',
  rivaServerUrl: 'localhost:50051',
  kokoroModel: 'kokoro-v0_19',
  kokoroVoice: 'hf_alpha',
  rivaVoice: 'Hindi.Female-1',
  browserVoice: '',
  enableVAD: true,
  maxSilenceMs: 1500,
}

// ─── Kokoro voices (kokoro-onnx speaker IDs) ──────────────────────────────────
const KOKORO_VOICES = [
  { group: '🇮🇳 Hindi', lang: 'hi-IN', voices: [
    { id: 'hf_alpha',   label: 'Alpha   — Hindi Female (Natural)', gender: 'female' },
    { id: 'hf_beta',    label: 'Beta    — Hindi Female (Warm)', gender: 'female' },
    { id: 'hm_omega',   label: 'Omega   — Hindi Male (Deep)', gender: 'male' },
  ]},
  { group: '🇺🇸 American Female', lang: 'en-US', voices: [
    { id: 'af_heart',   label: 'Heart   — Warm & natural (Best overall)', gender: 'female' },
    { id: 'af_bella',   label: 'Bella   — Smooth & clear', gender: 'female' },
    { id: 'af_nicole',  label: 'Nicole  — Soft & friendly', gender: 'female' },
    { id: 'af_aoede',   label: 'Aoede   — Expressive & lively', gender: 'female' },
    { id: 'af_kore',    label: 'Kore    — Calm & professional', gender: 'female' },
    { id: 'af_sarah',   label: 'Sarah   — Bright & energetic', gender: 'female' },
    { id: 'af_sky',     label: 'Sky     — Light & airy', gender: 'female' },
  ]},
  { group: '🇺🇸 American Male', lang: 'en-US', voices: [
    { id: 'am_adam',    label: 'Adam    — Deep & authoritative', gender: 'male' },
    { id: 'am_michael', label: 'Michael — Confident & clear', gender: 'male' },
    { id: 'am_fenrir',  label: 'Fenrir  — Bold & strong', gender: 'male' },
    { id: 'am_liam',    label: 'Liam    — Casual & approachable', gender: 'male' },
  ]},
  { group: '🇬🇧 British Female', lang: 'en-GB', voices: [
    { id: 'bf_emma',    label: 'Emma    — Elegant & precise', gender: 'female' },
    { id: 'bf_isabella',label: 'Isabella — Warm British accent', gender: 'female' },
  ]},
  { group: '🇬🇧 British Male', lang: 'en-GB', voices: [
    { id: 'bm_george',  label: 'George  — Classic British tone', gender: 'male' },
    { id: 'bm_lewis',   label: 'Lewis   — Modern British voice', gender: 'male' },
  ]},
]

// ─── NVIDIA Riva TTS voices ──────────────────────────────────────────────────
const RIVA_VOICES = [
  { group: '🇮🇳 Hindi', lang: 'hi-IN', voices: [
    { id: 'Hindi.Female-1',       label: 'Female-1  — Hindi Female', gender: 'female' },
    { id: 'Hindi.Male-1',         label: 'Male-1    — Hindi Male', gender: 'male' },
  ]},
  { group: '🇺🇸 English (US)', lang: 'en-US', voices: [
    { id: 'English-US.Female-1',  label: 'Female-1  — Natural (Default)', gender: 'female' },
    { id: 'English-US.Female-2',  label: 'Female-2  — Expressive', gender: 'female' },
    { id: 'English-US.Male-1',    label: 'Male-1    — Deep & clear', gender: 'male' },
    { id: 'English-US.Male-2',    label: 'Male-2    — Neutral', gender: 'male' },
  ]},
  { group: '🇬🇧 English (UK)', lang: 'en-GB', voices: [
    { id: 'English-UK.Female-1',  label: 'Female-1  — British Female', gender: 'female' },
    { id: 'English-UK.Male-1',    label: 'Male-1    — British Male', gender: 'male' },
  ]},
  { group: '🇩🇪 German', lang: 'de-DE', voices: [
    { id: 'German.Female-1',      label: 'Female-1  — German Female', gender: 'female' },
  ]},
  { group: '🇪🇸 Spanish', lang: 'es-ES', voices: [
    { id: 'Spanish-ES.Female-1',  label: 'Female-1  — Spanish Female', gender: 'female' },
  ]},
]

const STT_ENGINES = [
  {
    id: 'groq_whisper',
    name: 'Groq Whisper',
    description: 'Cloud API · whisper-large-v3 · ~1s latency',
    badge: 'Recommended',
    badgeColor: 'bg-blue-500/20 text-blue-400',
    requiresKey: 'groqApiKey',
    icon: '⚡',
  },
  {
    id: 'openai_whisper',
    name: 'OpenAI Whisper',
    description: 'Cloud API · whisper-1 · 99+ languages',
    badge: 'Cloud',
    badgeColor: 'bg-green-500/20 text-green-400',
    requiresKey: 'openaiApiKey',
    icon: '🌐',
  },
  {
    id: 'riva',
    name: 'NVIDIA Riva',
    description: 'On-device · Jetson GPU · ~50ms latency · Offline',
    badge: 'On-Device',
    badgeColor: 'bg-purple-500/20 text-purple-400',
    requiresKey: null,
    icon: '🔥',
  },
  {
    id: 'browser',
    name: 'Browser (Web Speech API)',
    description: 'Built-in browser STT · No API key · Variable quality',
    badge: 'Free',
    badgeColor: 'bg-gray-500/20 text-gray-400',
    requiresKey: null,
    icon: '🌍',
  },
]

const TTS_ENGINES = [
  {
    id: 'edge_tts',
    name: 'Microsoft Neural HD',
    description: 'Free Studio Quality · Madhur (Male) / Swara (Female) · Auto across any device',
    badge: 'Neural HD',
    badgeColor: 'bg-emerald-500/20 text-emerald-400',
    requiresKey: null,
    icon: '🎙️',
  },
  {
    id: 'browser',
    name: 'Browser TTS',
    description: 'Built-in · Zero latency · Multiple voices',
    badge: 'Free',
    badgeColor: 'bg-gray-500/20 text-gray-400',
    requiresKey: null,
    icon: '🔊',
  },
  {
    id: 'kokoro',
    name: 'Kokoro',
    description: 'Open-source · 82M params · Natural voice · Offline capable',
    badge: 'Open Source',
    badgeColor: 'bg-orange-500/20 text-orange-400',
    requiresKey: null,
    icon: '🎙️',
  },
  {
    id: 'elevenlabs',
    name: 'ElevenLabs',
    description: 'Cloud API · Ultra-realistic · Multilingual',
    badge: 'Premium',
    badgeColor: 'bg-yellow-500/20 text-yellow-400',
    requiresKey: 'elevenLabsApiKey',
    icon: '✨',
  },
  {
    id: 'riva_tts',
    name: 'NVIDIA Riva TTS',
    description: 'On-device · Jetson GPU · Low latency · Offline',
    badge: 'On-Device',
    badgeColor: 'bg-purple-500/20 text-purple-400',
    requiresKey: null,
    icon: '🔥',
  },
]

const LANGUAGES = [
  { code: 'en-US', label: 'English (US)' },
  { code: 'en-IN', label: 'English (India)' },
  { code: 'en-GB', label: 'English (UK)' },
  { code: 'hi-IN', label: 'Hindi (हिंदी)' },
  { code: 'es-ES', label: 'Spanish (España)' },
  { code: 'es-US', label: 'Spanish (US)' },
  { code: 'fr-FR', label: 'French (Français)' },
  { code: 'de-DE', label: 'German (Deutsch)' },
  { code: 'pt-BR', label: 'Portuguese (Brasil)' },
  { code: 'ja-JP', label: 'Japanese (日本語)' },
  { code: 'ko-KR', label: 'Korean (한국어)' },
  { code: 'zh-CN', label: 'Chinese (普通话)' },
  { code: 'ru-RU', label: 'Russian (Русский)' },
  { code: 'ar-SA', label: 'Arabic (العربية)' },
  { code: 'it-IT', label: 'Italian (Italiano)' },
]

const STORAGE_KEY = 'devavision_voice_settings'

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionHeader({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return (
    <div className="flex items-start gap-3 mb-5">
      <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
        {icon}
      </div>
      <div>
        <h3 className="font-semibold text-foreground">{title}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
    </div>
  )
}

function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
  formatValue,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  formatValue?: (v: number) => string
}) {
  const display = formatValue ? formatValue(value) : value.toFixed(1)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-foreground">{label}</label>
        <span className="text-sm font-mono text-primary bg-primary/10 px-2 py-0.5 rounded">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none bg-border accent-primary cursor-pointer"
      />
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  )
}

function EngineCard({
  engine,
  isSelected,
  onSelect,
}: {
  engine: (typeof STT_ENGINES)[0]
  isSelected: boolean
  onSelect: () => void
}) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        'w-full text-left p-4 rounded-xl border transition-all duration-200',
        isSelected
          ? 'border-primary bg-primary/10 shadow-[0_0_0_1px_rgba(99,102,241,0.3)]'
          : 'border-border bg-muted/10 hover:border-border/80 hover:bg-muted/20'
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="text-xl leading-none">{engine.icon}</span>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-sm text-foreground">{engine.name}</span>
              <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded-full', engine.badgeColor)}>
                {engine.badge}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">{engine.description}</p>
          </div>
        </div>
        <div
          className={cn(
            'w-4 h-4 rounded-full border-2 shrink-0 mt-0.5 transition-colors',
            isSelected ? 'border-primary bg-primary' : 'border-border'
          )}
        />
      </div>
    </button>
  )
}

function SecretInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-foreground flex items-center gap-1.5">
        <Key className="w-3.5 h-3.5 text-muted-foreground" />
        {label}
      </label>
      <div className="relative">
        <input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder || 'Enter API key...'}
          className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary pr-16"
        />
        <button
          type="button"
          onClick={() => setShow(!show)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded"
        >
          {show ? 'Hide' : 'Show'}
        </button>
      </div>
    </div>
  )
}

// Helper to heuristically detect gender from OS / browser voice names
function detectVoiceGender(name: string): 'female' | 'male' | 'unknown' {
  const lower = name.toLowerCase()
  if (
    lower.includes('female') ||
    lower.includes('woman') ||
    lower.includes('girl') ||
    lower.includes('zira') ||
    lower.includes('swara') ||
    lower.includes('kalpana') ||
    lower.includes('sara') ||
    lower.includes('jenny') ||
    lower.includes('aria') ||
    lower.includes('sonia') ||
    lower.includes('neerja') ||
    lower.includes(' गूगल') ||
    lower.includes('google हिन्दी')
  ) {
    return 'female'
  }
  if (
    lower.includes('male') ||
    lower.includes('man') ||
    lower.includes('boy') ||
    lower.includes('david') ||
    lower.includes('madhur') ||
    lower.includes('hemant') ||
    lower.includes('george') ||
    lower.includes('guy') ||
    lower.includes('mark')
  ) {
    return 'male'
  }
  return 'unknown'
}

function BrowserVoicePicker({
  value,
  onChange,
  selectedLang,
  selectedGender,
  speed,
  pitch,
  volume,
}: {
  value: string
  onChange: (v: string) => void
  selectedLang: string
  selectedGender: 'all' | 'female' | 'male'
  speed: number
  pitch: number
  volume: number
}) {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [isPlaying, setIsPlaying] = useState(false)

  useEffect(() => {
    const load = () => {
      const list = window.speechSynthesis?.getVoices() || []
      if (list.length > 0) setVoices(list)
    }
    load()
    window.speechSynthesis?.addEventListener('voiceschanged', load)
    return () => window.speechSynthesis?.removeEventListener('voiceschanged', load)
  }, [])

  if (voices.length === 0) {
    return (
      <div className="pt-2 border-t border-border/50">
        <p className="text-xs text-muted-foreground italic">
          Loading browser voices... (requires Chrome/Edge/Firefox with TTS support)
        </p>
      </div>
    )
  }

  // Filter voices by Language & Gender
  const langPrefix = selectedLang.split('-')[0] // 'hi' or 'en'
  const matchingLangVoices = voices.filter((v) => {
    const vLang = (v.lang || '').toLowerCase()
    return vLang.startsWith(langPrefix) || (selectedLang === 'hi-IN' && (v.name.includes('हिन्दी') || vLang.includes('hi')))
  })

  // Base list of voices matching language (or all voices if no language match)
  const baseVoices = matchingLangVoices.length > 0 ? matchingLangVoices : voices

  let filteredVoices = baseVoices.filter((v) => {
    if (selectedGender === 'all') return true
    const g = detectVoiceGender(v.name)
    if (g === 'unknown') return true
    return g === selectedGender
  })

  // If no native male/female voice exists in browser for this language, fallback to base voices with pitch modulation
  const isFallbackTuned = filteredVoices.length === 0 && baseVoices.length > 0
  if (isFallbackTuned) {
    filteredVoices = baseVoices
  }

  const playSample = (voiceName?: string) => {
    if (!window.speechSynthesis) return
    window.speechSynthesis.cancel()

    const targetVoiceName = voiceName || value
    const matchedVoice = voices.find((v) => v.name === targetVoiceName) || (baseVoices.length > 0 ? baseVoices[0] : undefined)

    const isFemaleVoice = matchedVoice ? detectVoiceGender(matchedVoice.name) === 'female' : true
    const isHindi = selectedLang.startsWith('hi') || (matchedVoice && matchedVoice.lang.startsWith('hi'))
    
    let sampleText = ''
    if (isHindi) {
      sampleText = selectedGender === 'female'
        ? 'नमस्ते! मैं देवा विज़न एआई हूँ। मैं आपके सीसीटीवी कैमरों का लाइव डेटा एनालाइज़ कर सकती हूँ।'
        : 'नमस्ते! मैं देवा विज़न एआई हूँ। मैं आपके सीसीटीवी कैमरों का लाइव डेटा एनालाइज़ कर सकता हूँ।'
    } else {
      sampleText = 'Hello! I am DevaVision AI. How can I assist you with your CCTV cameras today?'
    }

    const utterance = new SpeechSynthesisUtterance(sampleText)
    if (matchedVoice) utterance.voice = matchedVoice
    utterance.lang = selectedLang || 'hi-IN'
    utterance.rate = speed

    // Deep masculine pitch downshift (0.62x) for male preference on female browser voice
    if (selectedGender === 'male') {
      utterance.pitch = isFemaleVoice ? Math.max(0.5, pitch * 0.62) : pitch
    } else if (selectedGender === 'female') {
      utterance.pitch = !isFemaleVoice ? Math.min(1.6, pitch * 1.2) : pitch
    } else {
      utterance.pitch = pitch
    }

    utterance.volume = volume

    setIsPlaying(true)
    utterance.onend = () => setIsPlaying(false)
    utterance.onerror = () => setIsPlaying(false)

    window.speechSynthesis.speak(utterance)
  }

  return (
    <div className="pt-2 space-y-3 border-t border-border/50">
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-foreground">
            Browser Voice ({filteredVoices.length} available)
          </label>
          <button
            type="button"
            onClick={() => playSample()}
            className={cn(
              'text-xs px-2.5 py-1 rounded-lg flex items-center gap-1.5 font-medium transition-all shadow-sm',
              isPlaying
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                : 'bg-primary/15 text-primary border border-primary/30 hover:bg-primary/25'
            )}
          >
            <Volume2 className={cn('w-3.5 h-3.5', isPlaying && 'animate-pulse')} />
            {isPlaying ? 'Speaking...' : '🔊 Test Voice'}
          </button>
        </div>

        <select
          value={value}
          onChange={(e) => {
            onChange(e.target.value)
            playSample(e.target.value)
          }}
          className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary shadow-inner"
        >
          <option value="">System Default ({selectedLang})</option>
          {filteredVoices.map((v) => {
            const gender = detectVoiceGender(v.name)
            const genderLabel =
              selectedGender === 'male' && gender === 'female'
                ? ' [👨 Male Pitch-Shifted]'
                : gender === 'female'
                ? ' [👩 Female]'
                : gender === 'male'
                ? ' [👨 Male]'
                : ''
            return (
              <option key={v.name} value={v.name}>
                {v.name}{genderLabel} {v.localService ? '(offline)' : '(online)'}
              </option>
            )
          })}
        </select>
        <p className="text-xs text-muted-foreground">
          {isFallbackTuned
            ? `Browser only has 1 Hindi voice installed — automatically applying deep male pitch shift for male voice.`
            : `Filtered for ${selectedLang} (${selectedGender} voice preference).`}
        </p>
      </div>
    </div>
  )
}

// ─── Live Audio Preview Player Component ─────────────────────────────────────

function VoicePreviewPlayer({
  ttsEngine,
  voiceName,
  language,
  gender,
  speed,
  pitch,
  volume,
}: {
  ttsEngine: string
  voiceName: string
  language: string
  gender: 'all' | 'female' | 'male'
  speed: number
  pitch: number
  volume: number
}) {
  const [isPlaying, setIsPlaying] = useState(false)

  const speakSample = async () => {
    const isHindi = language.startsWith('hi')
    const sampleText = isHindi
      ? gender === 'female'
        ? 'नमस्ते! मैं देवा विज़न एआई हूँ। मैं आपके सीसीटीवी कैमरों का लाइव डेटा एनालाइज़ कर सकती हूँ। मैं आपकी क्या सहायता कर सकती हूँ?'
        : 'नमस्ते! मैं देवा विज़न एआई हूँ। मैं आपके सीसीटीवी कैमरों का लाइव डेटा एनालाइज़ कर सकता हूँ। मैं आपकी क्या सहायता कर सकता हूँ?'
      : 'Hello! I am DevaVision AI. How can I assist you with your CCTV cameras today?'

    // If Edge TTS (Microsoft Neural HD) is selected by the user, synthesize via backend
    if (ttsEngine === 'edge_tts') {
      setIsPlaying(true)
      try {
        const res = await api.post(
          '/api/tts/synthesize',
          {
            text: sampleText,
            language: language || 'hi-IN',
            gender: gender || 'male',
            speed: speed,
            pitch: pitch,
          },
          { responseType: 'blob' }
        )
        const audioUrl = URL.createObjectURL(res.data)
        const audio = new Audio(audioUrl)
        audio.volume = volume
        audio.onended = () => {
          setIsPlaying(false)
          URL.revokeObjectURL(audioUrl)
        }
        audio.onerror = () => {
          setIsPlaying(false)
          URL.revokeObjectURL(audioUrl)
        }
        await audio.play()
      } catch (err) {
        console.error('Edge TTS preview failed:', err)
        setIsPlaying(false)
      }
      return
    }

    if (!window.speechSynthesis) return
    window.speechSynthesis.cancel()

    const voices = window.speechSynthesis.getVoices()
    const targetVoice = voices.find((v) => v.name === voiceName) || 
      voices.find((v) => (v.lang || '').startsWith(language.split('-')[0])) || 
      (language.startsWith('hi') ? voices.find(v => v.name.includes('हिन्दी') || (v.lang || '').includes('hi')) : undefined)

    const isFemaleVoice = targetVoice ? detectVoiceGender(targetVoice.name) === 'female' : true

    const utterance = new SpeechSynthesisUtterance(sampleText)
    if (targetVoice) utterance.voice = targetVoice
    utterance.lang = language || 'hi-IN'
    utterance.rate = speed

    // If user wants Male voice but Chrome only provides a female voice, pitch-shift down to male timbre (0.62x)
    if (gender === 'male') {
      utterance.pitch = isFemaleVoice ? Math.max(0.5, pitch * 0.62) : pitch
    } else if (gender === 'female') {
      utterance.pitch = !isFemaleVoice ? Math.min(1.6, pitch * 1.2) : pitch
    } else {
      utterance.pitch = pitch
    }

    utterance.volume = volume

    setIsPlaying(true)
    utterance.onend = () => setIsPlaying(false)
    utterance.onerror = () => setIsPlaying(false)

    window.speechSynthesis.speak(utterance)
  }

  const isHindi = language.startsWith('hi')

  return (
    <div className="p-4 rounded-2xl bg-gradient-to-r from-primary/10 via-card to-primary/5 border border-primary/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-lg">
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-xl bg-primary/20 border border-primary/30 flex items-center justify-center shrink-0">
          <Volume2 className={cn('w-6 h-6 text-primary', isPlaying && 'animate-pulse text-amber-400')} />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-primary">Live Voice Preview</span>
            {isPlaying && (
              <span className="flex items-center gap-1 text-[10px] text-amber-400 font-semibold px-2 py-0.5 rounded-full bg-amber-400/10 border border-amber-400/20">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" /> Speaking...
              </span>
            )}
          </div>
          <p className="text-sm font-semibold text-foreground mt-0.5">
            {voiceName || 'System Default Voice'} ({gender === 'female' ? '👩 Female' : gender === 'male' ? '👨 Male' : 'Default'})
          </p>
          <p className="text-xs text-muted-foreground italic mt-0.5">
            "{isHindi ? (gender === 'female' ? 'नमस्ते! मैं देवा विज़न एआई हूँ, मैं सहायता कर सकती हूँ...' : 'नमस्ते! मैं देवा विज़न एआई हूँ, मैं सहायता कर सकता हूँ...') : 'Hello! I am DevaVision AI...'}"
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={speakSample}
        className={cn(
          'w-full sm:w-auto px-5 py-2.5 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-md',
          isPlaying
            ? 'bg-amber-500 text-black shadow-amber-500/20 animate-pulse'
            : 'bg-primary text-white hover:bg-primary/90 shadow-primary/20 hover:scale-[1.02]'
        )}
      >
        <Volume2 className="w-4 h-4" />
        {isPlaying ? 'Playing Sample...' : '▶ Listen Voice Preview'}
      </button>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function VoiceAssistantTab() {
  const [settings, setSettings] = useState<VoiceSettings>(DEFAULT_SETTINGS)
  const [saved, setSaved] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const addToast = useToastStore((s) => s.addToast)

  // Load from backend config and localStorage on mount
  useEffect(() => {
    let localData: Partial<VoiceSettings> = {}
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) localData = JSON.parse(stored)
    } catch {}

    api.get('/api/config')
      .then((res) => {
        const c = res.data || {}
        setSettings((prev) => ({
          ...DEFAULT_SETTINGS,
          ...localData,
          sttEngine: c.VOICE_STT_ENGINE || localData.sttEngine || prev.sttEngine,
          ttsEngine: c.VOICE_TTS_ENGINE || localData.ttsEngine || prev.ttsEngine,
          language: c.VOICE_LANGUAGE || localData.language || prev.language,
          voiceGender: c.VOICE_GENDER || localData.voiceGender || prev.voiceGender,
          speechSpeed: c.VOICE_SPEED !== undefined ? c.VOICE_SPEED : (localData.speechSpeed ?? prev.speechSpeed),
          speechPitch: c.VOICE_PITCH !== undefined ? c.VOICE_PITCH : (localData.speechPitch ?? prev.speechPitch),
          speechVolume: c.VOICE_VOLUME !== undefined ? c.VOICE_VOLUME : (localData.speechVolume ?? prev.speechVolume),
          browserVoice: c.VOICE_NAME || localData.browserVoice || prev.browserVoice,
          kokoroVoice: c.VOICE_KOKORO_VOICE || localData.kokoroVoice || prev.kokoroVoice,
          rivaVoice: c.VOICE_RIVA_VOICE || localData.rivaVoice || prev.rivaVoice,
          rivaServerUrl: c.VOICE_RIVA_SERVER || localData.rivaServerUrl || prev.rivaServerUrl,
          groqApiKey: c.GROQ_API_KEY && c.GROQ_API_KEY !== '***' ? c.GROQ_API_KEY : (localData.groqApiKey || ''),
        }))
      })
      .catch(() => {
        if (Object.keys(localData).length > 0) {
          setSettings((prev) => ({ ...prev, ...localData }))
        }
      })
  }, [])

  const update = <K extends keyof VoiceSettings>(key: K, value: VoiceSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  const handleSave = async () => {
    setIsSaving(true)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))

      const updates: Record<string, any> = {
        VOICE_STT_ENGINE: settings.sttEngine,
        VOICE_TTS_ENGINE: settings.ttsEngine,
        VOICE_LANGUAGE: settings.language,
        VOICE_GENDER: settings.voiceGender,
        VOICE_SPEED: settings.speechSpeed,
        VOICE_PITCH: settings.speechPitch,
        VOICE_VOLUME: settings.speechVolume,
        VOICE_NAME: settings.browserVoice,
        VOICE_RIVA_SERVER: settings.rivaServerUrl,
        VOICE_KOKORO_VOICE: settings.kokoroVoice,
        VOICE_RIVA_VOICE: settings.rivaVoice,
      }
      if (settings.groqApiKey) updates.GROQ_API_KEY = settings.groqApiKey
      if (settings.openaiApiKey) updates.OPENAI_API_KEY = settings.openaiApiKey

      await api.post('/api/config', { updates })

      setSaved(true)
      addToast({
        title: 'Voice Settings Saved',
        message: 'Voice assistant configuration successfully saved to backend.',
        type: 'success',
      })
      setTimeout(() => setSaved(false), 3500)
    } catch (err: any) {
      addToast({
        title: 'Save Error',
        message: err.message || 'Failed to save voice settings to backend',
        type: 'danger',
      })
    } finally {
      setIsSaving(false)
    }
  }

  const selectedStt = STT_ENGINES.find((e) => e.id === settings.sttEngine)
  const selectedTts = TTS_ENGINES.find((e) => e.id === settings.ttsEngine)

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500/20 to-blue-500/20 flex items-center justify-center">
          <Mic className="w-5 h-5 text-violet-400" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-foreground">Voice Assistant</h2>
          <p className="text-sm text-muted-foreground">Configure STT engine, TTS voice, language, and performance</p>
        </div>
      </div>

      {/* Live Voice Preview Bar */}
      <VoicePreviewPlayer
        ttsEngine={settings.ttsEngine}
        voiceName={settings.browserVoice || (settings.ttsEngine === 'kokoro' ? settings.kokoroVoice : settings.ttsEngine === 'riva_tts' ? settings.rivaVoice : '')}
        language={settings.language}
        gender={settings.voiceGender}
        speed={settings.speechSpeed}
        pitch={settings.speechPitch}
        volume={settings.speechVolume}
      />

      {/* ── STT Engine ──────────────────────────────────────────────────── */}
      <div className="bg-muted/10 border border-border rounded-2xl p-6 space-y-4">
        <SectionHeader
          icon={<Mic className="w-4 h-4 text-primary" />}
          title="Speech-to-Text Engine"
          description="Converts your spoken words into text. Choose based on latency, privacy, and language needs."
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {STT_ENGINES.map((engine) => (
            <EngineCard
              key={engine.id}
              engine={engine}
              isSelected={settings.sttEngine === engine.id}
              onSelect={() => update('sttEngine', engine.id)}
            />
          ))}
        </div>

        {/* Engine-specific config */}
        {selectedStt?.requiresKey === 'groqApiKey' && (
          <div className="pt-2 space-y-3 border-t border-border/50">
            <SecretInput
              label="Groq API Key"
              value={settings.groqApiKey}
              onChange={(v) => update('groqApiKey', v)}
              placeholder="gsk_xxxxxxxxxxxxxxxxxxxx"
            />
            <a
              href="https://console.groq.com/keys"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary hover:underline inline-flex items-center gap-1"
            >
              <Info className="w-3 h-3" /> Get a free Groq API key →
            </a>
          </div>
        )}

        {selectedStt?.requiresKey === 'openaiApiKey' && (
          <div className="pt-2 space-y-3 border-t border-border/50">
            <SecretInput
              label="OpenAI API Key"
              value={settings.openaiApiKey}
              onChange={(v) => update('openaiApiKey', v)}
              placeholder="sk-xxxxxxxxxxxxxxxxxxxx"
            />
          </div>
        )}

        {settings.sttEngine === 'riva' && (
          <div className="pt-2 space-y-3 border-t border-border/50">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-foreground">Riva gRPC Server URL</label>
              <input
                type="text"
                value={settings.rivaServerUrl}
                onChange={(e) => update('rivaServerUrl', e.target.value)}
                placeholder="localhost:50051"
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Info className="w-3 h-3" />
                Jetson Riva server address. Run <code className="bg-muted px-1 rounded">riva_start.sh</code> on the Jetson first.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ── TTS Engine ──────────────────────────────────────────────────── */}
      <div className="bg-muted/10 border border-border rounded-2xl p-6 space-y-4">
        <SectionHeader
          icon={<Volume2 className="w-4 h-4 text-primary" />}
          title="Text-to-Speech Engine"
          description="Converts AI responses to spoken audio. Kokoro is the best offline option."
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {TTS_ENGINES.map((engine) => (
            <EngineCard
              key={engine.id}
              engine={engine}
              isSelected={settings.ttsEngine === engine.id}
              onSelect={() => update('ttsEngine', engine.id)}
            />
          ))}
        </div>

        {/* TTS engine-specific config */}
        {settings.ttsEngine === 'elevenlabs' && (
          <div className="pt-2 space-y-3 border-t border-border/50">
            <SecretInput
              label="ElevenLabs API Key"
              value={settings.elevenLabsApiKey}
              onChange={(v) => update('elevenLabsApiKey', v)}
              placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            />
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-foreground">Voice ID</label>
              <input
                type="text"
                value={settings.elevenLabsVoiceId}
                onChange={(e) => update('elevenLabsVoiceId', e.target.value)}
                placeholder="21m00Tcm4TlvDq8ikWAM"
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <a
                href="https://elevenlabs.io/voice-library"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-primary hover:underline inline-flex items-center gap-1"
              >
                <Info className="w-3 h-3" /> Browse ElevenLabs voices →
              </a>
            </div>
          </div>
        )}

        {settings.ttsEngine === 'kokoro' && (
          <div className="pt-2 space-y-4 border-t border-border/50">
            <div className="flex items-start gap-2 p-3 rounded-lg bg-orange-500/10 border border-orange-500/20">
              <Info className="w-4 h-4 text-orange-400 shrink-0 mt-0.5" />
              <p className="text-xs text-orange-300">
                Kokoro runs locally on the backend. Install with:{' '}
                <code className="bg-black/30 px-1 rounded">pip install kokoro-onnx</code>.
                No API key — fully offline and private.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Model */}
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-foreground">Model</label>
                <select
                  value={settings.kokoroModel}
                  onChange={(e) => update('kokoroModel', e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary shadow-inner"
                >
                  <option value="kokoro-v0_19">kokoro-v0_19 — Best quality</option>
                  <option value="kokoro-v0_19-half">kokoro-v0_19-half — Faster / smaller</option>
                </select>
              </div>

              {/* Voice / Speaker */}
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-foreground">
                  Voice / Speaker ({settings.voiceGender} voice)
                </label>
                <select
                  value={settings.kokoroVoice}
                  onChange={(e) => update('kokoroVoice', e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary shadow-inner"
                >
                  {KOKORO_VOICES.map((group) => {
                    const filtered = group.voices.filter(
                      (v) => settings.voiceGender === 'all' || v.gender === settings.voiceGender
                    )
                    if (filtered.length === 0) return null
                    return (
                      <optgroup key={group.group} label={group.group}>
                        {filtered.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.label}
                          </option>
                        ))}
                      </optgroup>
                    )
                  })}
                </select>
                <p className="text-xs text-muted-foreground">
                  Selected: <code className="bg-muted px-1 rounded text-primary">{settings.kokoroVoice}</code>
                </p>
              </div>
            </div>
          </div>
        )}

        {settings.ttsEngine === 'riva_tts' && (
          <div className="pt-2 space-y-4 border-t border-border/50">
            <div className="flex items-start gap-2 p-3 rounded-lg bg-purple-500/10 border border-purple-500/20">
              <Info className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
              <p className="text-xs text-purple-300">
                Voice availability depends on which language packs are installed on your Riva server.
                Run <code className="bg-black/30 px-1 rounded">riva_start.sh</code> with the desired language pack.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-foreground">Riva gRPC Server</label>
                <input
                  type="text"
                  value={settings.rivaServerUrl}
                  onChange={(e) => update('rivaServerUrl', e.target.value)}
                  placeholder="localhost:50051"
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary shadow-inner"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-foreground">Voice</label>
                <select
                  value={settings.rivaVoice}
                  onChange={(e) => update('rivaVoice', e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary shadow-inner"
                >
                  {RIVA_VOICES.map((group) => {
                    const filtered = group.voices.filter(
                      (v) => settings.voiceGender === 'all' || v.gender === settings.voiceGender
                    )
                    if (filtered.length === 0) return null
                    return (
                      <optgroup key={group.group} label={group.group}>
                        {filtered.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.label}
                          </option>
                        ))}
                      </optgroup>
                    )
                  })}
                </select>
                <p className="text-xs text-muted-foreground">
                  Voice ID: <code className="bg-muted px-1 rounded text-primary">{settings.rivaVoice}</code>
                </p>
              </div>
            </div>
          </div>
        )}

        {settings.ttsEngine === 'browser' && (
          <BrowserVoicePicker
            value={settings.browserVoice}
            onChange={(v) => update('browserVoice', v)}
            selectedLang={settings.language}
            selectedGender={settings.voiceGender}
            speed={settings.speechSpeed}
            pitch={settings.speechPitch}
            volume={settings.speechVolume}
          />
        )}
      </div>

      {/* ── Language & Voice Gender ────────────────────────────────────────── */}
      <div className="bg-muted/10 border border-border rounded-2xl p-6 space-y-6">
        <SectionHeader
          icon={<Globe className="w-4 h-4 text-primary" />}
          title="Language & Voice Preference"
          description="Primary language for speech recognition and responses with Male / Female voice options."
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Recognition Language */}
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-foreground">Primary Language</label>
            <select
              value={settings.language}
              onChange={(e) => update('language', e.target.value)}
              className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary shadow-inner text-foreground font-medium"
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              Select Hindi, English, or other languages. Speech recognition will adapt automatically.
            </p>
          </div>

          {/* Voice Gender Preference */}
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-foreground">Voice Gender</label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => update('voiceGender', 'female')}
                className={cn(
                  'py-2.5 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition-all',
                  settings.voiceGender === 'female'
                    ? 'border-pink-500 bg-pink-500/15 text-pink-400 shadow-sm'
                    : 'border-border bg-background/50 text-muted-foreground hover:bg-muted/30'
                )}
              >
                👩 Female
              </button>
              <button
                type="button"
                onClick={() => update('voiceGender', 'male')}
                className={cn(
                  'py-2.5 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition-all',
                  settings.voiceGender === 'male'
                    ? 'border-blue-500 bg-blue-500/15 text-blue-400 shadow-sm'
                    : 'border-border bg-background/50 text-muted-foreground hover:bg-muted/30'
                )}
              >
                👨 Male
              </button>
              <button
                type="button"
                onClick={() => update('voiceGender', 'all')}
                className={cn(
                  'py-2.5 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition-all',
                  settings.voiceGender === 'all'
                    ? 'border-primary bg-primary/15 text-primary shadow-sm'
                    : 'border-border bg-background/50 text-muted-foreground hover:bg-muted/30'
                )}
              >
                🌐 All
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              Filters TTS voices so you only get your preferred male or female voice options.
            </p>
          </div>
        </div>
      </div>

      {/* ── Voice Quality ─────────────────────────────────────────────────── */}
      <div className="bg-muted/10 border border-border rounded-2xl p-6 space-y-5">
        <SectionHeader
          icon={<Volume2 className="w-4 h-4 text-primary" />}
          title="Voice Quality"
          description="Adjust speech speed, pitch, and volume for the AI voice responses."
        />

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <SliderField
            label="Speech Speed"
            value={settings.speechSpeed}
            min={0.5}
            max={2.0}
            step={0.1}
            onChange={(v) => update('speechSpeed', v)}
            formatValue={(v) => `${v.toFixed(1)}×`}
          />
          <SliderField
            label="Pitch"
            value={settings.speechPitch}
            min={0.5}
            max={2.0}
            step={0.1}
            onChange={(v) => update('speechPitch', v)}
            formatValue={(v) => `${v.toFixed(1)}×`}
          />
          <SliderField
            label="Volume"
            value={settings.speechVolume}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => update('speechVolume', v)}
            formatValue={(v) => `${Math.round(v * 100)}%`}
          />
        </div>
      </div>

      {/* ── Advanced / VAD ─────────────────────────────────────────────────── */}
      <div className="bg-muted/10 border border-border rounded-2xl overflow-hidden">
        <button
          onClick={() => setAdvancedOpen(!advancedOpen)}
          className="w-full flex items-center justify-between px-6 py-4 hover:bg-muted/20 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Zap className="w-4 h-4 text-primary" />
            <span className="font-semibold text-foreground text-sm">Advanced / VAD Settings</span>
          </div>
          {advancedOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
        </button>

        {advancedOpen && (
          <div className="px-6 pb-6 space-y-5 border-t border-border/50">
            <div className="pt-4">
              <label className="flex items-center gap-3 cursor-pointer group">
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={settings.enableVAD}
                    onChange={(e) => update('enableVAD', e.target.checked)}
                    className="sr-only"
                  />
                  <div
                    className={cn(
                      'w-10 h-5 rounded-full transition-colors duration-200',
                      settings.enableVAD ? 'bg-primary' : 'bg-border'
                    )}
                  />
                  <div
                    className={cn(
                      'absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform duration-200',
                      settings.enableVAD ? 'translate-x-5' : 'translate-x-0'
                    )}
                  />
                </div>
                <div>
                  <span className="font-medium text-sm text-foreground">Voice Activity Detection (VAD)</span>
                  <p className="text-xs text-muted-foreground">Only process audio when speech is detected. Reduces API calls.</p>
                </div>
              </label>
            </div>

            {settings.enableVAD && (
              <SliderField
                label="VAD Sensitivity"
                value={settings.vadSensitivity}
                min={0.1}
                max={1.0}
                step={0.05}
                onChange={(v) => update('vadSensitivity', v)}
                formatValue={(v) => {
                  if (v < 0.35) return `${v.toFixed(2)} (Low)`
                  if (v < 0.7) return `${v.toFixed(2)} (Medium)`
                  return `${v.toFixed(2)} (High)`
                }}
              />
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-foreground">
                Max Silence Before Stop (ms)
              </label>
              <input
                type="number"
                min={500}
                max={5000}
                step={100}
                value={settings.maxSilenceMs}
                onChange={(e) => update('maxSilenceMs', parseInt(e.target.value))}
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary max-w-[180px]"
              />
              <p className="text-xs text-muted-foreground">
                How long to wait after speech stops before sending to STT. Lower = faster, higher = more accurate.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ── Save Button ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="flex items-center gap-2 px-6 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary/90 transition-colors shadow-lg shadow-primary/20 disabled:opacity-50"
        >
          {isSaving ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : saved ? (
            <CheckCircle className="w-4 h-4" />
          ) : (
            <Zap className="w-4 h-4" />
          )}
          {isSaving ? 'Saving to Backend...' : saved ? 'Saved!' : 'Save Settings'}
        </button>

        {saved && (
          <span className="text-sm text-green-400 flex items-center gap-1.5 font-medium">
            <CheckCircle className="w-4 h-4" />
            Configuration saved & synced with backend
          </span>
        )}

        <div className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
          <AlertCircle className="w-3.5 h-3.5 text-primary" />
          Persisted to backend database & configuration
        </div>
      </div>
    </div>
  )
}
