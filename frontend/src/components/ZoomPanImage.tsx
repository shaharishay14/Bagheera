import { useCallback, useEffect, useRef, useState } from 'react';

interface Props {
  src: string;
  alt: string;
  /** Extra classes for the outer viewport (e.g. rounded, border, aspect). */
  className?: string;
  /** Max zoom factor. Default 6×. */
  maxScale?: number;
}

const MIN_SCALE = 1;
const WHEEL_STEP = 0.0015; // sensitivity per wheel delta unit
const BUTTON_STEP = 1.4; // multiplicative zoom per +/- click

interface Transform {
  scale: number;
  tx: number;
  ty: number;
}

/**
 * Hand-rolled zoom/pan image viewer — no external dependency.
 *
 * Supports mouse-wheel zoom (toward the cursor), drag-to-pan, and explicit
 * ＋ / － / reset buttons. Zoom is scoped to the image only: the wheel listener
 * is non-passive and calls preventDefault, so the page never scrolls. Panning
 * is clamped so the scaled image always covers the viewport (the picture can't
 * get lost). At scale 1 the image fits exactly and pan is locked; the cursor
 * only becomes a grab handle once zoomed in.
 *
 * The authoritative transform lives in a ref (`tfRef`) so wheel/pointer math
 * reads fresh values synchronously; React state mirrors it purely for render.
 */
export default function ZoomPanImage({ src, alt, className = '', maxScale = 6 }: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const tfRef = useRef<Transform>({ scale: 1, tx: 0, ty: 0 });
  const [tf, setTf] = useState<Transform>({ scale: 1, tx: 0, ty: 0 });
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  const [grabbing, setGrabbing] = useState(false);

  // Clamp a candidate transform so the scaled image always covers the viewport
  // — no empty gutters, image never lost. transformOrigin is 0 0, so valid
  // translation ranges are [viewport - content, 0] on each axis.
  const clamp = useCallback((t: Transform): Transform => {
    const vp = viewportRef.current;
    const img = imgRef.current;
    const scale = Math.min(maxScale, Math.max(MIN_SCALE, t.scale));
    if (!vp || !img) return { scale, tx: t.tx, ty: t.ty };
    const vw = vp.clientWidth;
    const vh = vp.clientHeight;
    // offsetWidth/Height are the layout size at scale 1 (transform is visual).
    const contentW = img.offsetWidth * scale;
    const contentH = img.offsetHeight * scale;
    const minX = Math.min(0, vw - contentW);
    const minY = Math.min(0, vh - contentH);
    return {
      scale,
      tx: Math.min(0, Math.max(minX, t.tx)),
      ty: Math.min(0, Math.max(minY, t.ty)),
    };
  }, [maxScale]);

  const commit = useCallback((t: Transform) => {
    const c = clamp(t);
    tfRef.current = c;
    setTf(c);
  }, [clamp]);

  // Zoom to a target scale while keeping the viewport-relative anchor fixed.
  const zoomTo = useCallback((nextScale: number, anchorX: number, anchorY: number) => {
    const cur = tfRef.current;
    const scale = Math.min(maxScale, Math.max(MIN_SCALE, nextScale));
    if (scale === cur.scale) return;
    // Content coordinate currently under the anchor, held invariant.
    const cx = (anchorX - cur.tx) / cur.scale;
    const cy = (anchorY - cur.ty) / cur.scale;
    commit({ scale, tx: anchorX - cx * scale, ty: anchorY - cy * scale });
  }, [commit, maxScale]);

  // Native non-passive wheel listener: scope zoom to the image, never the page.
  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = vp.getBoundingClientRect();
      zoomTo(tfRef.current.scale * (1 - e.deltaY * WHEEL_STEP), e.clientX - rect.left, e.clientY - rect.top);
    };
    vp.addEventListener('wheel', onWheel, { passive: false });
    return () => vp.removeEventListener('wheel', onWheel);
  }, [zoomTo]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (tfRef.current.scale <= MIN_SCALE) return;
    dragRef.current = { x: e.clientX, y: e.clientY };
    setGrabbing(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    const dx = e.clientX - drag.x;
    const dy = e.clientY - drag.y;
    dragRef.current = { x: e.clientX, y: e.clientY };
    const cur = tfRef.current;
    commit({ scale: cur.scale, tx: cur.tx + dx, ty: cur.ty + dy });
  };
  const endDrag = (e: React.PointerEvent) => {
    if (!dragRef.current) return;
    dragRef.current = null;
    setGrabbing(false);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* pointer already released */
    }
  };

  const zoomByButton = (factor: number) => {
    const vp = viewportRef.current;
    const ax = vp ? vp.clientWidth / 2 : 0;
    const ay = vp ? vp.clientHeight / 2 : 0;
    zoomTo(tfRef.current.scale * factor, ax, ay);
  };
  const reset = () => commit({ scale: 1, tx: 0, ty: 0 });

  const zoomed = tf.scale > MIN_SCALE;

  return (
    <div ref={viewportRef} className={`group relative overflow-hidden bg-surface-subtle ${className}`}>
      <img
        ref={imgRef}
        src={src}
        alt={alt}
        draggable={false}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onLoad={() => commit(tfRef.current)}
        style={{
          transform: `translate(${tf.tx}px, ${tf.ty}px) scale(${tf.scale})`,
          transformOrigin: '0 0',
          cursor: zoomed ? (grabbing ? 'grabbing' : 'grab') : 'default',
          touchAction: 'none',
        }}
        className="block w-full select-none"
      />

      {/* Zoom controls — real, focusable buttons. */}
      <div className="absolute right-2 top-2 flex flex-col gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <ZoomButton label="Zoom in" disabled={tf.scale >= maxScale} onClick={() => zoomByButton(BUTTON_STEP)}>
          +
        </ZoomButton>
        <ZoomButton label="Zoom out" disabled={tf.scale <= MIN_SCALE} onClick={() => zoomByButton(1 / BUTTON_STEP)}>
          −
        </ZoomButton>
        <ZoomButton label="Reset zoom" disabled={!zoomed} onClick={reset}>
          <ResetIcon />
        </ZoomButton>
      </div>

      {zoomed ? (
        <span className="pointer-events-none absolute bottom-2 left-2 rounded-full bg-ink/70 px-2 py-0.5 text-[10px] font-semibold text-white">
          {tf.scale.toFixed(1)}×
        </span>
      ) : null}
    </div>
  );
}

function ZoomButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="flex h-7 w-7 items-center justify-center rounded-md border border-border-strong bg-surface/90 text-sm font-bold leading-none text-ink shadow-card backdrop-blur hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
    >
      {children}
    </button>
  );
}

function ResetIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <path d="M3 3v5h5" />
    </svg>
  );
}
