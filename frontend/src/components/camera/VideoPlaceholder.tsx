import React, { memo, useEffect, useRef, useState } from 'react'
import { cn } from '@/utils/utils'
import { webrtcStreamManager } from '@/services/webrtcStreamManager'

export interface VideoPlayerProps {
  cameraId: string
  poster?: string
  loading?: boolean
  error?: string
  streamUrl?: string
}

export const VideoPlayer = memo(({ cameraId, poster, loading, error, streamUrl }: VideoPlayerProps) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [hasFirstFrame, setHasFirstFrame] = useState(false);
  const [useFallback, setUseFallback] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const fallbackUrl = streamUrl || `/api/cameras/${cameraId}/stream`;

  useEffect(() => {
    if (loading || error) return;
    setConnectionError(null);
    setUseFallback(false);
    setHasFirstFrame(false);

    // Fallback to MJPEG stream if WebRTC doesn't connect in 3 seconds
    const timer = setTimeout(() => {
      setUseFallback(true);
    }, 3000);

    const unsubscribe = webrtcStreamManager.subscribe(cameraId, (stream, err) => {
      if (err) {
        setUseFallback(true);
        return;
      }

      if (stream && videoRef.current) {
        if (videoRef.current.srcObject !== stream) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
        setHasFirstFrame(true);
        setConnectionError(null);
        clearTimeout(timer);
      }
    });

    return () => {
      clearTimeout(timer);
      unsubscribe();
    };
  }, [cameraId, loading, error]);

  if (error || connectionError) {
    return (
      <div className="w-full h-full relative bg-black/90 flex flex-col items-center justify-center p-4">
        <span className="text-danger font-mono text-xs tracking-widest uppercase text-center">
          {error || connectionError}
        </span>
        <button 
          onClick={() => {
            setConnectionError(null);
            setUseFallback(false);
            webrtcStreamManager.closeStream(cameraId);
          }}
          className="mt-3 px-3 py-1 bg-primary/20 hover:bg-primary/30 border border-primary/40 rounded text-[11px] text-primary transition-colors font-mono"
        >
          Reconnect
        </button>
      </div>
    );
  }

  return (
    <div className="w-full h-full relative bg-black flex items-center justify-center overflow-hidden">
      {useFallback ? (
        <img
          src={fallbackUrl}
          className="w-full h-full object-cover"
          alt={`Live feed ${cameraId}`}
          onError={() => {
            setConnectionError("Stream offline");
          }}
        />
      ) : (
        <>
          {poster && !hasFirstFrame && (
            <img 
              src={poster} 
              className="absolute inset-0 w-full h-full object-cover opacity-20" 
              alt={`Poster for ${cameraId}`}
            />
          )}
          
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            onLoadedData={() => setHasFirstFrame(true)}
            onPlaying={() => setHasFirstFrame(true)}
            className={cn(
              "w-full h-full object-cover transition-opacity duration-200",
              hasFirstFrame ? "opacity-100" : "opacity-0"
            )}
          />

          {(!hasFirstFrame || loading) && (
            <div className="absolute inset-0 z-10 bg-black flex flex-col items-center justify-center p-4 pointer-events-none">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mb-3" />
              <span className="text-foreground/60 font-mono text-xs tracking-widest uppercase">
                {loading ? "Initializing Stream..." : "Connecting Stream..."}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
});

VideoPlayer.displayName = 'VideoPlayer';
