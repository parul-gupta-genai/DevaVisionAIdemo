import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Send, Mic, MicOff, Volume2, VolumeX, Activity, AlertCircle, Fingerprint, ShieldAlert, Users, ChevronRight, Cpu, MemoryStick } from 'lucide-react';
import { api } from '../../api/api';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/utils/utils';
import { useAppStore } from '@/store/useAppStore';

interface Message {
  text: string;
  isBot: boolean;
  isPartial?: boolean;
  isError?: boolean;
}

type VoiceState = "IDLE" | "LISTENING" | "TRANSCRIBING" | "WAITING_FOR_RESPONSE" | "SPEAKING" | "ERROR";

// Component for rendering Rich UI Cards from AI text markers
const RichUICard = ({ type }: { type: string }) => {
  if (type === 'SAFETY_REPORT') {
    return (
      <div className="mt-3 bg-danger/10 border border-danger/30 rounded-xl p-4 flex flex-col gap-3 shadow-lg">
        <div className="flex items-center gap-2 text-danger">
          <ShieldAlert className="w-5 h-5" />
          <span className="font-bold">17 Violations Detected</span>
        </div>
        <div className="text-xs text-danger/80">Past 24 hours (Hardhat & Fire Zone violations)</div>
        <button className="flex items-center justify-between w-full bg-danger/20 hover:bg-danger text-danger hover:text-white px-3 py-2 rounded-lg transition-colors font-bold text-xs mt-1 border border-danger/30">
          <span>View Evidence</span>
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    );
  }
  if (type === 'WORKER_STATS') {
    return (
      <div className="mt-3 bg-primary/10 border border-primary/30 rounded-xl p-4 flex flex-col gap-3 shadow-lg">
        <div className="flex items-center gap-2 text-primary">
          <Users className="w-5 h-5" />
          <span className="font-bold">0 People Active</span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <div className="bg-background/40 py-2 rounded-lg border border-foreground/10"><div className="font-black text-white text-lg">0</div>Workers</div>
          <div className="bg-background/40 py-2 rounded-lg border border-foreground/10"><div className="font-black text-white text-lg">0</div>Staff</div>
          <div className="bg-background/40 py-2 rounded-lg border border-foreground/10"><div className="font-black text-white text-lg">0</div>Visitors</div>
        </div>
        <button className="flex items-center justify-between w-full bg-primary/20 hover:bg-primary text-primary hover:text-white px-3 py-2 rounded-lg transition-colors font-bold text-xs mt-1 border border-primary/30">
          <span>View Live Dashboard</span>
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    );
  }
  return null;
}

const AIChatWidget: React.FC = () => {
  const { isAIChatOpen, toggleAIChat } = useAppStore();
  
  const getInitialGreeting = () => {
    try {
      const stored = localStorage.getItem('devavision_voice_settings');
      if (stored) {
        const vs = JSON.parse(stored);
        const isHindi = vs.language?.startsWith('hi');
        const isFemale = vs.voiceGender === 'female' || (vs.browserVoice && vs.browserVoice.includes('हिन्दी'));
        if (isHindi) {
          return isFemale
            ? 'नमस्ते! मैं देवा विज़न एआई हूँ। आज मैं आपके सीसीटीवी डेटा के विश्लेषण में क्या सहायता कर सकती हूँ?'
            : 'नमस्ते! मैं देवा विज़न एआई हूँ। आज मैं आपके सीसीटीवी डेटा के विश्लेषण में क्या सहायता कर सकता हूँ?';
        }
      }
    } catch {}
    return "Hello! I'm DevaVision AI. How can I help you analyze the camera data today?";
  };

  const [messages, setMessages] = useState<Message[]>([
    { text: getInitialGreeting(), isBot: true }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  const [voiceState, setVoiceState] = useState<VoiceState>("IDLE");
  const [speakerEnabled, setSpeakerEnabled] = useState(true);
  
  // Telemetry state for CPU/RAM/GPU
  const [telemetry, setTelemetry] = useState<any>(null);
  // Fetch telemetry similar to TopNav
  useEffect(() => {
    const fetchTelemetry = async () => {
      try {
        const res = await api.get('/api/telemetry');
        setTelemetry(res.data);
      } catch (e) {}
    };
    fetchTelemetry();
    const int = setInterval(fetchTelemetry, 2000);
    return () => clearInterval(int);
  }, []);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const autoSendTimerRef = useRef<any>(null);
  const handsFreeRef = useRef<boolean>(true);
  const [handsFreeMode, setHandsFreeMode] = useState<boolean>(true);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isAIChatOpen) {
      setTimeout(scrollToBottom, 100);
    }
  }, [messages, voiceState, isAIChatOpen]);

  // Request Mobile / Desktop Push Notification Permission on Mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().catch(() => {});
    }
  }, []);

  const resumeListeningIfHandsFree = () => {
    if (!handsFreeRef.current) return;
    setTimeout(() => {
      try {
        if (recognitionRef.current) {
          let vs: any = {};
          try {
            const stored = localStorage.getItem('devavision_voice_settings');
            if (stored) vs = JSON.parse(stored);
          } catch (e) {}
          if (vs.language) recognitionRef.current.lang = vs.language;
          recognitionRef.current.start();
        }
      } catch (e) {
        // Ignore already started or abort errors
      }
    }, 450);
  };

  useEffect(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      recognition.lang = 'hi-IN';
      
      recognition.onstart = () => transitionTo("LISTENING");
      
      recognition.onresult = (event: any) => {
        let interimTranscript = '';
        let finalTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript;
          else interimTranscript += event.results[i][0].transcript;
        }
        
        const currentText = (finalTranscript || interimTranscript).trim();
        if (currentText) {
          setInput(currentText);
          
          // Clear any pending silence timer
          if (autoSendTimerRef.current) clearTimeout(autoSendTimerRef.current);
          
          // Auto-submit when user finishes speaking (No Enter key required)
          if (finalTranscript && finalTranscript.trim().length > 1) {
            autoSendTimerRef.current = setTimeout(() => {
              handleSend(finalTranscript.trim());
            }, 400);
          } else if (interimTranscript && interimTranscript.trim().length > 2) {
            autoSendTimerRef.current = setTimeout(() => {
              handleSend(interimTranscript.trim());
            }, 1000);
          }
        }
      };
      
      recognition.onerror = (event: any) => {
        if (event.error !== 'aborted') {
          transitionTo("ERROR", `Microphone error: ${event.error}`);
        }
      };
      
      recognition.onend = () => {
        if (voiceState === "LISTENING" || voiceState === "TRANSCRIBING") {
          transitionTo("IDLE");
        }
      };
      
      recognitionRef.current = recognition;
    }
    
    return () => forceCleanup();
  }, []);

  const transitionTo = (newState: VoiceState, errorMsg?: string) => {
    setVoiceState(newState);
    if (errorMsg) setMessages(prev => [...prev, { text: `[System]: ${errorMsg}`, isBot: true, isError: true }]);
    if (newState === "IDLE" || newState === "ERROR") {
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (e) {}
      }
      setIsLoading(false);
    }
  };

  const forceCleanup = () => {
    handsFreeRef.current = false;
    if (autoSendTimerRef.current) clearTimeout(autoSendTimerRef.current);
    transitionTo("IDLE");
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  };

// Helper to heuristically detect gender from voice names
function detectVoiceGender(name: string): 'female' | 'male' | 'unknown' {
  const lower = name.toLowerCase();
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
    return 'female';
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
    return 'male';
  }
  return 'unknown';
}

  const playTTS = (text: string) => {
    if (!speakerEnabled) {
      resumeListeningIfHandsFree();
      return;
    }
    
    // Fast cancel and resume to clear audio queue
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    
    // Clean markdown, symbols, URLs and brackets for zero-latency instant playback
    const cleanText = text
      .replace(/\[.*?\]/g, '')
      .replace(/[*_#`~>]/g, '')
      .replace(/https?:\/\/\S+/g, '')
      .trim();
    if (!cleanText) {
      resumeListeningIfHandsFree();
      return;
    }

    // Read stored voice settings
    let vs: any = {};
    try {
      const stored = localStorage.getItem('devavision_voice_settings');
      if (stored) vs = JSON.parse(stored);
    } catch (e) {}

    // Dynamic Sentiment & Emotional Modulation (आवाज़ का उतार-चढ़ाव)
    const lower = cleanText.toLowerCase();
    const isUrgent = /fire|smoke|danger|hazard|alert|warning|threat|intrusion|weapon|alarm|emergency|आग|धुआं|खतरा|सावधान|घुसपैठ|चेतावनी|इमरजेंसी/.test(lower);
    const isQuestion = cleanText.endsWith('?') || cleanText.includes('क्या') || cleanText.includes('how') || cleanText.includes('why') || cleanText.includes('कहाँ') || cleanText.includes('कब');

    // Trigger Mobile / Desktop Notification if Alert
    if (isUrgent && 'Notification' in window && Notification.permission === 'granted') {
      try {
        new Notification('🚨 DevaVision AI Security Alert', {
          body: cleanText,
          icon: '/favicon.ico',
        });
      } catch (e) {}
    }

    let effectiveRate = vs.speechSpeed || 1.0;
    let effectivePitch = vs.speechPitch || 1.0;

    // Sentiment modulation
    if (isUrgent) {
      effectiveRate = Math.min(2.0, effectiveRate * 1.06); // Crisp pace
      effectivePitch = Math.min(2.0, effectivePitch * 1.10); // Alert pitch
    } else if (isQuestion) {
      effectivePitch = Math.min(2.0, effectivePitch * 1.04); // Inquiring upward inflection
    }

    // If Edge TTS (Microsoft Neural HD) is chosen, stream studio audio from backend
    if (vs.ttsEngine === 'edge_tts') {
      transitionTo("SPEAKING");
      api.post(
        '/api/tts/synthesize',
        {
          text: cleanText,
          language: vs.language || 'hi-IN',
          gender: vs.voiceGender || 'male',
          speed: effectiveRate,
          pitch: effectivePitch,
        },
        { responseType: 'blob' }
      )
        .then((res) => {
          const audioUrl = URL.createObjectURL(res.data);
          const audio = new Audio(audioUrl);
          audio.volume = vs.speechVolume !== undefined ? vs.speechVolume : 1.0;
          audio.onended = () => {
            transitionTo("IDLE");
            URL.revokeObjectURL(audioUrl);
            resumeListeningIfHandsFree();
          };
          audio.onerror = () => {
            transitionTo("IDLE");
            URL.revokeObjectURL(audioUrl);
            resumeListeningIfHandsFree();
          };
          audio.play().catch(() => {
            transitionTo("IDLE");
            resumeListeningIfHandsFree();
          });
        })
        .catch((err) => {
          console.error('Edge TTS playback failed:', err);
          transitionTo("IDLE");
          resumeListeningIfHandsFree();
        });
      return;
    }

    const voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
    let targetVoice: SpeechSynthesisVoice | undefined;

    if (vs.browserVoice) {
      targetVoice = voices.find(v => v.name === vs.browserVoice);
    }
    if (!targetVoice && vs.language) {
      const langPrefix = vs.language.split('-')[0];
      targetVoice = voices.find(v => (v.lang || '').toLowerCase().startsWith(langPrefix) || (vs.language.startsWith('hi') && (v.name.includes('हिन्दी') || (v.lang || '').includes('hi'))));
    }

    const isFemaleVoice = targetVoice ? detectVoiceGender(targetVoice.name) === 'female' : true;

    // Gender pitch synthesis for browser TTS fallback
    if (vs.voiceGender === 'male') {
      effectivePitch = isFemaleVoice ? Math.max(0.5, effectivePitch * 0.62) : effectivePitch;
    } else if (vs.voiceGender === 'female') {
      effectivePitch = !isFemaleVoice ? Math.min(1.6, effectivePitch * 1.2) : effectivePitch;
    }

    const utterance = new SpeechSynthesisUtterance(cleanText);
    if (targetVoice) utterance.voice = targetVoice;
    utterance.lang = vs.language || 'hi-IN';
    utterance.rate = effectiveRate;
    utterance.pitch = effectivePitch;
    utterance.volume = vs.speechVolume !== undefined ? vs.speechVolume : 1.0;

    utterance.onstart = () => transitionTo("SPEAKING");
    utterance.onend = () => {
      transitionTo("IDLE");
      resumeListeningIfHandsFree();
    };
    utterance.onerror = () => {
      transitionTo("IDLE");
      resumeListeningIfHandsFree();
    };

    // Clear any suspended browser speech queue
    if (window.speechSynthesis.paused) {
      window.speechSynthesis.resume();
    }
    window.speechSynthesis.speak(utterance);
  };

  // Track whether microphone permission has been granted
  const [micGranted, setMicGranted] = useState(false);

  useEffect(() => {
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then(() => {
        setMicGranted(true);
      })
      .catch((err) => {
        setMicGranted(false);
      });
  }, []);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      transitionTo("ERROR", "Web Speech API is not supported in this browser.");
      return;
    }

    if (voiceState === "LISTENING" || voiceState === "TRANSCRIBING") {
      handsFreeRef.current = false;
      try {
        recognitionRef.current.stop();
      } catch (e) {}
      transitionTo("IDLE");
      return;
    }

    // Enable hands-free mode and start listening
    handsFreeRef.current = true;
    try {
      let vs: any = {};
      try {
        const stored = localStorage.getItem('devavision_voice_settings');
        if (stored) vs = JSON.parse(stored);
      } catch (e) {}
      if (vs.language) {
        recognitionRef.current.lang = vs.language;
      }
      recognitionRef.current.start();
    } catch (e: any) {
      if (e.message?.includes('already started')) {
        transitionTo("LISTENING");
      } else {
        transitionTo("ERROR", `Microphone error: ${e.message || e}`);
      }
    }
  };











  const handleSend = async (textToSend?: string) => {
    const messageText = typeof textToSend === 'string' ? textToSend.trim() : input.trim();
    if (!messageText) return;

    setMessages(prev => [...prev, { text: messageText, isBot: false }]);
    setInput('');
    setIsLoading(true);
    transitionTo("WAITING_FOR_RESPONSE");

    try {
      let botResponse = "";
      
      // Advanced Tech: Smart Parser Mocking for enterprise demo
      const lowerText = messageText.toLowerCase();
      if (lowerText.includes('violation') || lowerText.includes('safety') || lowerText.includes('fire')) {
        await new Promise(r => setTimeout(r, 1200));
        botResponse = "I have analyzed the events across all cameras for the past 24 hours. Here is the summary:\n[SAFETY_REPORT]";
      } else if (lowerText.includes('worker') || lowerText.includes('people') || lowerText.includes('staff')) {
        await new Promise(r => setTimeout(r, 1000));
        botResponse = "Currently, there are 0 people detected on site based on active camera tracking.\n[WORKER_STATS]";
      } else {
        const res = await api.post('/api/chat', { message: messageText, camera_id: "global" });
        botResponse = res.data.response;
      }
      
      setMessages(prev => [...prev, { text: botResponse, isBot: true }]);
      
      if (speakerEnabled) playTTS(botResponse);
      else transitionTo("IDLE");
    } catch (error: any) {
      setMessages(prev => [...prev, { text: "The AI service is temporarily unavailable. Please try again later.", isBot: true, isError: true }]);
      transitionTo("ERROR");
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSend();
  };

  const getStatusBadge = () => {
    switch (voiceState) {
      case "LISTENING":
        return (
          <span className="flex items-center gap-1.5 text-emerald-400 font-semibold tracking-wide">
            <Mic size={13} className="animate-pulse" /> 🎙️ Listening... (Auto-sends when you pause)
          </span>
        );
      case "TRANSCRIBING":
      case "WAITING_FOR_RESPONSE":
        return (
          <span className="flex items-center gap-1.5 text-primary font-semibold tracking-wide">
            <div className="animate-spin h-3 w-3 border-2 border-primary rounded-full border-t-transparent"></div> Processing query...
          </span>
        );
      case "SPEAKING":
        return (
          <span className="flex items-center gap-1.5 text-amber-400 font-semibold tracking-wide">
            <Volume2 size={13} className="animate-bounce" /> Speaking response... (Auto-listens next)
          </span>
        );
      case "ERROR":
        return (
          <span className="flex items-center gap-1.5 text-danger font-semibold tracking-wide">
            <AlertCircle size={13} /> Error Occurred
          </span>
        );
      default:
        return null;
    }
  };

  const renderMessageText = (text: string) => {
    const parts = text.split(/(\[SAFETY_REPORT\]|\[WORKER_STATS\])/g);
    return (
      <>
        {parts.map((part, i) => {
          if (part === '[SAFETY_REPORT]') return <RichUICard key={i} type="SAFETY_REPORT" />;
          if (part === '[WORKER_STATS]') return <RichUICard key={i} type="WORKER_STATS" />;
          return <span key={i} className="whitespace-pre-wrap">{part}</span>;
        })}
      </>
    );
  };

  return (
    <>
      {/* Backdrop */}
      <AnimatePresence>
        {isAIChatOpen && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={toggleAIChat}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[90]"
          />
        )}
      </AnimatePresence>

      {/* Right Drawer */}
      <AnimatePresence>
        {isAIChatOpen && (
          <motion.div 
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="fixed top-0 right-0 bottom-0 w-full sm:w-[450px] glass-pro border-l border-foreground/10 z-[100] flex flex-col shadow-[-20px_0_50px_rgba(0,0,0,0.5)]"
          >
            {/* Header */}
            <div className="p-5 border-b border-foreground/10 bg-background/40 flex justify-between items-center relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-primary/20 rounded-full blur-[40px] -mr-10 -mt-10 pointer-events-none" />
              <div className="flex items-center gap-3 relative z-10">
                <div className="w-10 h-10 rounded-xl bg-primary/20 border border-primary/50 flex items-center justify-center shadow-[0_0_15px_rgba(0,112,243,0.3)]">
                  <Fingerprint className="text-primary w-5 h-5" />
                </div>
                <div className="flex-1">
                  <h3 className="font-black text-sm text-white tracking-wide">DevaVision AI</h3>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse glow-success" /> 
                    <span className="text-[10px] text-success font-bold tracking-widest uppercase">Orin NX Edge Inference</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 relative z-10">
                <button onClick={() => setSpeakerEnabled(!speakerEnabled)} className="p-2 bg-foreground/5 hover:bg-foreground/10 rounded-lg transition-colors border border-foreground/10 text-muted-foreground hover:text-white">
                  {speakerEnabled ? <Volume2 size={16} /> : <VolumeX size={16} />}
                </button>
                <button onClick={toggleAIChat} className="p-2 bg-foreground/5 hover:bg-danger/20 hover:text-danger hover:border-danger/30 rounded-lg transition-colors border border-foreground/10 text-muted-foreground">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Chat Area */}
            <div className="flex-1 p-5 overflow-y-auto custom-scrollbar flex flex-col gap-6 relative">
              <div className="absolute inset-0 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />
              
              {messages.map((msg, idx) => (
                <motion.div 
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  key={idx} 
                  className={`flex ${msg.isBot ? 'justify-start' : 'justify-end'} relative z-10`}
                >
                  {msg.isBot && (
                    <div className="w-8 h-8 rounded-xl bg-primary/20 border border-primary/50 flex items-center justify-center shrink-0 mr-3 mt-0 mb-1">
                      <Fingerprint className="w-4 h-4 text-primary" />
                    </div>
                  )}
                  <div className={cn(
                    "max-w-[85%] rounded-2xl p-3 text-sm shadow-md flex flex-col",
                    msg.isBot 
                      ? (msg.isError ? 'bg-danger/10 text-danger border border-danger/30 rounded-tl-sm' : 'glass-panel border-foreground/10 text-foreground/90 rounded-tl-sm')
                      : 'bg-primary text-white rounded-tr-sm glow-primary',
                    msg.isPartial ? 'opacity-70 italic' : ''
                  )}>
                    {renderMessageText(msg.text)}
                  </div>
                </motion.div>
              ))}
              
              {(isLoading || voiceState === "WAITING_FOR_RESPONSE") && (
                <div className="flex justify-start relative z-10">
                  <div className="w-8 h-8 rounded-xl bg-primary/20 border border-primary/50 flex items-center justify-center shrink-0 mr-3 mt-0 mb-1">
                    <Fingerprint className="w-4 h-4 text-primary animate-pulse" />
                  </div>
                  <div className="glass-panel border-foreground/10 text-white rounded-2xl rounded-tl-sm p-4 text-sm flex gap-1.5 items-center">
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce"></span>
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce delay-75"></span>
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce delay-150"></span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Quick Prompts */}
            <div className="px-4 pb-2 flex gap-2 overflow-x-auto custom-scrollbar whitespace-nowrap hide-scrollbar">
              <button onClick={() => handleSend("kitne workers site par hain?")} className="px-3 py-1.5 bg-foreground/5 hover:bg-primary/20 border border-foreground/10 hover:border-primary/50 rounded-full text-xs transition-colors">
                👷 Active Workers?
              </button>
              <button onClick={() => handleSend("pichle 24 ghante mein safety violations dikhao")} className="px-3 py-1.5 bg-foreground/5 hover:bg-primary/20 border border-foreground/10 hover:border-primary/50 rounded-full text-xs transition-colors">
                ⚠️ Recent Violations
              </button>
            </div>

            {voiceState !== "IDLE" && (
              <div className="bg-background/60 border-t border-foreground/5 px-4 py-2 flex items-center gap-3 justify-center text-[10px] font-bold tracking-widest uppercase text-primary glow-primary">
                 {getStatusBadge()}
              </div>
            )}

            {/* Input Area */}
            <div className="p-4 bg-background/60 border-t border-foreground/10 backdrop-blur-md pb-8 sm:pb-4">
              <div className="relative flex items-center gap-3">
                <button
                  type="button"
                  title="Click to start/stop voice input"
                  onClick={toggleListening}
                  className={cn(
                    "p-3.5 rounded-xl transition-all duration-300 shadow-lg flex shrink-0 items-center justify-center",
                    voiceState === "LISTENING" || voiceState === "TRANSCRIBING"
                      ? 'bg-danger/20 text-danger border border-danger/50 glow-danger animate-pulse'
                      : 'bg-foreground/5 text-muted-foreground border border-foreground/10 hover:bg-foreground/10 hover:text-white'
                  )}
                >
                  {voiceState === "LISTENING" || voiceState === "TRANSCRIBING" ? <MicOff size={18} /> : <Mic size={18} />}
                </button>
                
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyPress}
                    placeholder="Query DevaVision AI..."
                    disabled={voiceState !== "IDLE" && voiceState !== "ERROR"}
                    className="w-full bg-background/80 text-white border border-foreground/10 rounded-xl pl-4 pr-12 py-3.5 text-sm focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 disabled:opacity-50 transition-all placeholder-white/30"
                  />
                  <button 
                    onClick={() => handleSend()}
                    disabled={!input.trim() || isLoading || (voiceState !== "IDLE" && voiceState !== "ERROR")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 bg-primary text-white p-2 rounded-lg hover:bg-primary/80 disabled:bg-foreground/5 disabled:text-foreground/20 transition-all"
                  >
                    <Send size={16} />
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

export default AIChatWidget;
