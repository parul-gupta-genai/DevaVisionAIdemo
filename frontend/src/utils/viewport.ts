// DeepStream mux space — all analytics geometry lives in these coordinates.
export const VIDEO_W = 1280
export const VIDEO_H = 720

export interface ContainViewport {
  offsetX: number
  offsetY: number
  scaleX: number
  scaleY: number
}

/**
 * Maps the 1280x720 video space onto an object-contain container: where the
 * letterboxed/pillarboxed video actually renders and at what scale. Shared by
 * AnalyticsOverlay (drawing) and CountingLineEditor (drawing + inverse
 * mapping) — the two MUST use identical math or drawn lines land on
 * different pixels than the overlay renders and the plugin counts.
 */
export function computeContainViewport(
  containerW: number,
  containerH: number,
  videoEl?: HTMLVideoElement | null,
): ContainViewport {
  const rawAspect = (videoEl?.videoWidth && videoEl?.videoHeight)
    ? (videoEl.videoWidth / videoEl.videoHeight)
    : (VIDEO_W / VIDEO_H)

  const containerAspect = containerW / (containerH || 1)

  let renderW = containerW
  let renderH = containerH
  let offsetX = 0
  let offsetY = 0

  if (containerAspect > rawAspect) {
    // Container is wider -> pillarbox (bars on left and right)
    renderW = containerH * rawAspect
    renderH = containerH
    offsetX = (containerW - renderW) / 2
  } else {
    // Container is taller -> letterbox (bars on top and bottom)
    renderW = containerW
    renderH = containerW / rawAspect
    offsetY = (containerH - renderH) / 2
  }

  return { offsetX, offsetY, scaleX: renderW / VIDEO_W, scaleY: renderH / VIDEO_H }
}
