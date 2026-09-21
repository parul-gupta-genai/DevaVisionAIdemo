import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Camera, Check, RefreshCcw, RefreshCw, ChevronRight, CheckCircle2, AlertCircle, Upload, Image as ImageIcon } from 'lucide-react';
import axios from 'axios';

export const VisitorRegistration = () => {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({ name: '', email: '' });
  const [photos, setPhotos] = useState<{ front: string; left: string; right: string }>({ front: '', left: '', right: '' });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const searchParams = new URLSearchParams(window.location.search);
  const roleParam = searchParams.get('role');
  const role = roleParam && roleParam.toLowerCase() === 'employee' ? 'EMPLOYEE' : 'VISITOR';
  
  const [isSuccess, setIsSuccess] = useState(false);
  const [facingMode, setFacingMode] = useState<'user' | 'environment'>('user');
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isStartingCamera, setIsStartingCamera] = useState(false);
  
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const stopCamera = useCallback(() => {
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => {
        track.stop();
      });
      setMediaStream(null);
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, [mediaStream]);

  const startCamera = useCallback(async (mode: 'user' | 'environment' = 'user') => {
    setIsStartingCamera(true);
    setCameraError(null);

    // Check if mediaDevices API is supported (requires HTTPS or localhost)
    if (!navigator?.mediaDevices?.getUserMedia) {
      setCameraError("Camera access requires a secure context (HTTPS or localhost) or is not supported by this browser.");
      setIsStartingCamera(false);
      return;
    }

    // Stop existing stream first
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop());
      setMediaStream(null);
    }

    let stream: MediaStream | null = null;

    // 1. Try with preferred facingMode
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: mode,
          width: { ideal: 640 },
          height: { ideal: 640 }
        },
        audio: false
      });
    } catch (err: any) {
      console.warn("FacingMode constraint failed, trying basic video:", err);
    }

    // 2. Fallback to basic video constraint
    if (!stream) {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      } catch (err: any) {
        console.error("Camera access failed completely:", err);
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          setCameraError("Camera permission denied. Please allow camera access in your browser settings or upload photos below.");
        } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
          setCameraError("Camera is in use by another application. Please close other camera apps or upload photos.");
        } else {
          setCameraError("Unable to access camera. Please check your camera connection or upload photos.");
        }
      }
    }

    if (stream) {
      setMediaStream(stream);
      setCameraError(null);
    }
    setIsStartingCamera(false);
  }, [mediaStream]);

  // Bind media stream whenever the video element mounts or stream updates
  useEffect(() => {
    if (videoRef.current && mediaStream) {
      videoRef.current.srcObject = mediaStream;
      videoRef.current.onloadedmetadata = () => {
        videoRef.current?.play().catch(err => {
          console.warn("Video play failed:", err);
        });
      };
    }
  }, [mediaStream, step]);

  const toggleCamera = useCallback(async () => {
    const nextMode = facingMode === 'user' ? 'environment' : 'user';
    setFacingMode(nextMode);
    await startCamera(nextMode);
  }, [facingMode, startCamera]);

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  const capturePhoto = (angle: 'front' | 'left' | 'right'): string => {
    if (videoRef.current && canvasRef.current) {
      const context = canvasRef.current.getContext('2d');
      const w = videoRef.current.videoWidth || 640;
      const h = videoRef.current.videoHeight || 640;
      if (context && w > 0) {
        canvasRef.current.width = w;
        canvasRef.current.height = h;
        context.drawImage(videoRef.current, 0, 0, w, h);
        const base64 = canvasRef.current.toDataURL('image/jpeg', 0.85);
        return base64;
      }
    }
    return '';
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>, angle: 'front' | 'left' | 'right') => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const base64 = event.target?.result as string;
      if (base64) {
        const updated = { ...photos, [angle]: base64 };
        setPhotos(updated);

        if (step < 4) {
          setStep(step + 1);
        } else {
          submitRegistration(updated);
        }
      }
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const submitRegistration = async (finalPhotos = photos) => {
    setIsSubmitting(true);
    try {
      // Pick whatever photo is available as fallback for all 3 angles
      const front = finalPhotos.front || finalPhotos.left || finalPhotos.right;
      const left = finalPhotos.left || front;
      const right = finalPhotos.right || front;

      if (!front) {
        alert("Please capture or upload at least one photo before submitting.");
        setIsSubmitting(false);
        return;
      }

      await axios.post('/api/plugins/visitor/register', {
        name: formData.name,
        email: formData.email,
        role: role,
        photo_front: front,
        photo_left: left,
        photo_right: right
      });
      setIsSuccess(true);
      stopCamera();
    } catch (error: any) {
      console.error("Registration failed:", error);
      const msg = error.response?.data?.detail || "Registration failed. Please ensure your photo is clear and try again.";
      alert(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isSuccess) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex flex-col items-center justify-center p-6 text-center">
        <div className="bg-gradient-to-br from-indigo-500/20 to-purple-600/20 p-8 rounded-full mb-8 shadow-[0_0_50px_rgba(99,102,241,0.3)]">
          <CheckCircle2 className="w-24 h-24 text-indigo-400" />
        </div>
        <h1 className="text-4xl font-extrabold text-white mb-4 bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400">Registration Complete!</h1>
        <p className="text-zinc-400 text-lg max-w-sm">
          You can now proceed to the entrance. The DevaVision AI cameras will recognize you automatically.
        </p>
      </div>
    );
  }

  const currentAngle: 'front' | 'left' | 'right' = step === 2 ? 'front' : step === 3 ? 'left' : 'right';
  const hasAtLeastOnePhoto = Boolean(photos.front || photos.left || photos.right);

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white flex flex-col max-w-md mx-auto relative overflow-hidden">
      {/* Background glow effects */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-600/30 blur-[100px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/30 blur-[100px] rounded-full pointer-events-none" />

      <div className="p-8 z-10 flex-1 flex flex-col">
        <div className="flex flex-col items-center mb-6 text-center">
          <img src="/Hero_Homes.png" alt="Hero Homes Logo" className="w-auto h-20 mb-4 rounded-xl shadow-lg" />
          <h1 className="text-3xl font-extrabold mb-2 tracking-widest uppercase">Welcome to Hero Homes</h1>
          <p className="text-zinc-400 font-medium">
            {role === 'EMPLOYEE' ? 'Employee Self-Registration' : 'Visitor Self-Registration'}
          </p>
        </div>

        {step === 1 && (
          <div className="space-y-6 flex-1 flex flex-col justify-center">
            <div className="bg-foreground/5 backdrop-blur-xl border border-foreground/10 p-6 rounded-3xl shadow-xl">
              <div className="mb-6">
                <label className="block text-sm font-semibold mb-2 text-indigo-200">Full Name</label>
                <input 
                  type="text" 
                  className="w-full bg-background/50 border border-foreground/10 rounded-2xl px-5 py-4 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 transition-all text-white placeholder-white/30"
                  value={formData.name}
                  onChange={e => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. John Doe"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-2 text-indigo-200">Email Address (Optional)</label>
                <input 
                  type="email" 
                  className="w-full bg-background/50 border border-foreground/10 rounded-2xl px-5 py-4 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 transition-all text-white placeholder-white/30"
                  value={formData.email}
                  onChange={e => setFormData({ ...formData, email: e.target.value })}
                  placeholder="john@example.com"
                />
              </div>
            </div>
            <button 
              disabled={!formData.name.trim()}
              onClick={() => { setStep(2); startCamera(); }}
              className="w-full bg-gradient-to-r from-indigo-500 to-purple-600 text-white py-4 rounded-2xl font-bold flex items-center justify-center gap-2 disabled:opacity-50 shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 transition-all active:scale-[0.98]"
            >
              Continue to Face Scan <ChevronRight className="w-5 h-5" />
            </button>
          </div>
        )}

        {[2, 3, 4].includes(step) && (
          <div className="flex flex-col items-center flex-1 justify-center">
            <div className="text-center mb-4">
              <h2 className="text-2xl font-bold mb-1">Face Capture</h2>
              <p className="text-indigo-300 font-medium">Step {step - 1} of 3</p>
            </div>

            {/* Hidden file input for camera/photo fallback */}
            <input 
              ref={fileInputRef}
              type="file" 
              accept="image/*" 
              capture="user"
              className="hidden" 
              onChange={(e) => handleFileUpload(e, currentAngle)}
            />
            
            {cameraError ? (
              <div className="w-full aspect-square bg-red-950/20 border-2 border-red-500/40 rounded-3xl p-6 flex flex-col items-center justify-center text-center mb-6">
                <AlertCircle className="w-12 h-12 text-red-400 mb-3" />
                <p className="text-sm text-red-200 mb-4">{cameraError}</p>
                <div className="flex flex-col gap-2 w-full">
                  <button
                    onClick={() => startCamera(facingMode)}
                    className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-xl font-semibold text-sm transition-all"
                  >
                    Retry Camera
                  </button>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full py-2.5 bg-white/10 hover:bg-white/20 border border-white/20 rounded-xl font-semibold text-sm transition-all flex items-center justify-center gap-2"
                  >
                    <Upload className="w-4 h-4" /> Upload / Take Photo
                  </button>
                </div>
              </div>
            ) : (
              <div className="relative w-full aspect-square bg-background/50 rounded-full overflow-hidden mb-6 border-4 border-indigo-500/50 shadow-[0_0_30px_rgba(99,102,241,0.2)]">
                {photos[currentAngle] ? (
                  <img 
                    src={photos[currentAngle]} 
                    alt={`Preview ${currentAngle}`} 
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <video 
                    ref={videoRef} 
                    autoPlay 
                    playsInline 
                    muted 
                    className={`w-full h-full object-cover ${facingMode === 'user' ? 'transform scale-x-[-1]' : ''}`} 
                  />
                )}
                <canvas ref={canvasRef} className="hidden" />
                
                {isStartingCamera && (
                  <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center text-center p-4">
                    <RefreshCcw className="w-8 h-8 animate-spin text-indigo-400 mb-2" />
                    <span className="text-xs text-zinc-300">Starting camera...</span>
                  </div>
                )}

                <div className="absolute inset-0 pointer-events-none flex flex-col items-center justify-end pb-8">
                  <span className="bg-background/70 backdrop-blur-md px-6 py-3 rounded-full text-sm font-bold text-white shadow-xl border border-foreground/10">
                    {step === 2 && "Face Center (Front View)"}
                    {step === 3 && "Turn Head Left (Side View)"}
                    {step === 4 && "Turn Head Right (Side View)"}
                  </span>
                </div>
              </div>
            )}

            {/* Steps indicator & Photo thumbnails */}
            <div className="flex items-center gap-3 mb-6">
              {(['front', 'left', 'right'] as const).map((ang, idx) => (
                <div 
                  key={ang}
                  onClick={() => setStep(idx + 2)}
                  className={`flex flex-col items-center gap-1 cursor-pointer transition-all ${
                    idx + 2 === step ? 'scale-110 font-bold text-indigo-300' : 'text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  <div className={`w-10 h-10 rounded-xl overflow-hidden border flex items-center justify-center text-xs ${
                    idx + 2 === step 
                      ? 'border-indigo-500 bg-indigo-500/20' 
                      : photos[ang] 
                        ? 'border-emerald-500 bg-emerald-500/20' 
                        : 'border-zinc-700 bg-zinc-800'
                  }`}>
                    {photos[ang] ? (
                      <img src={photos[ang]} alt={ang} className="w-full h-full object-cover" />
                    ) : (
                      idx + 1
                    )}
                  </div>
                  <span className="text-[10px] capitalize">{ang}</span>
                </div>
              ))}
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-6">
              <button
                type="button"
                onClick={toggleCamera}
                title={facingMode === 'user' ? 'Switch to Back Camera' : 'Switch to Front Camera'}
                className="w-14 h-14 bg-white/10 hover:bg-white/20 text-white rounded-full flex flex-col items-center justify-center transition-all active:scale-95 border border-white/10 shadow-lg"
              >
                <RefreshCw className="w-5 h-5 text-indigo-300" />
                <span className="text-[10px] text-zinc-300 font-medium mt-0.5">{facingMode === 'user' ? 'Front' : 'Back'}</span>
              </button>

              <button 
                onClick={() => {
                  const angle = currentAngle;
                  const base64 = capturePhoto(angle) || photos[angle];
                  const updated = { ...photos, [angle]: base64 };
                  setPhotos(updated);
                  
                  if (step < 4) {
                    setStep(step + 1);
                  } else {
                    submitRegistration(updated);
                  }
                }}
                disabled={isSubmitting}
                className="w-20 h-20 bg-white text-indigo-600 rounded-full flex items-center justify-center active:scale-95 transition-all shadow-[0_0_30px_rgba(255,255,255,0.3)] hover:scale-105"
              >
                {isSubmitting ? (
                  <RefreshCcw className="w-8 h-8 animate-spin" />
                ) : (
                  <Camera className="w-8 h-8" />
                )}
              </button>

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                title="Upload Photo / Take with Phone Camera"
                className="w-14 h-14 bg-white/10 hover:bg-white/20 text-white rounded-full flex flex-col items-center justify-center transition-all active:scale-95 border border-white/10 shadow-lg"
              >
                <Upload className="w-5 h-5 text-indigo-300" />
                <span className="text-[10px] text-zinc-300 font-medium mt-0.5">Upload</span>
              </button>
            </div>

            {/* Direct Finish Registration button if at least 1 photo exists */}
            {hasAtLeastOnePhoto && (
              <button
                onClick={() => submitRegistration(photos)}
                disabled={isSubmitting}
                className="mt-6 text-xs text-indigo-300 hover:text-white underline font-semibold flex items-center gap-1"
              >
                {isSubmitting ? "Submitting..." : "Finish Registration with current photo(s) →"}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default VisitorRegistration;
