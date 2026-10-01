'use client';

/**
 * Motion shared by Account Selection, Analytics and My Activity.
 *
 * Everything here degrades to the final, static state: content is visible
 * without JavaScript or CSS animation, and under prefers-reduced-motion the
 * parallax stops, numbers land immediately and movement becomes a fade. The
 * matching CSS (the `as-` classes) is in globals.css.
 */

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Pointer and scroll parallax. Writes --as-px/--as-py (pointer, -1..1, eased
 * toward the cursor so layers glide) and --as-sy (scroll, px, capped) on the
 * element. Scroll comes from `scrollRef` when given, else the window. The
 * animation loop runs only while something is moving.
 */
export function useParallax(ref: React.RefObject<HTMLElement>, scrollRef?: React.RefObject<HTMLElement>) {
  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    const scroller: HTMLElement | Window = scrollRef?.current ?? window;
    const scrollTop = () => (scroller instanceof Window ? scroller.scrollY : scroller.scrollTop);

    let tx = 0, ty = 0, cx = 0, cy = 0, sy = -1, raf = 0;
    const tick = () => {
      cx += (tx - cx) * 0.08;
      cy += (ty - cy) * 0.08;
      el.style.setProperty('--as-px', cx.toFixed(4));
      el.style.setProperty('--as-py', cy.toFixed(4));
      const s = Math.min(scrollTop(), 400);
      if (s !== sy) {
        sy = s;
        el.style.setProperty('--as-sy', String(s));
      }
      raf = Math.abs(tx - cx) > 0.001 || Math.abs(ty - cy) > 0.001 ? requestAnimationFrame(tick) : 0;
    };
    const kick = () => { if (!raf) raf = requestAnimationFrame(tick); };
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse') return;
      tx = (e.clientX / window.innerWidth) * 2 - 1;
      ty = (e.clientY / window.innerHeight) * 2 - 1;
      kick();
    };
    const onLeave = () => { tx = 0; ty = 0; kick(); };

    window.addEventListener('pointermove', onMove, { passive: true });
    document.addEventListener('pointerleave', onLeave);
    scroller.addEventListener('scroll', kick, { passive: true });
    kick();
    return () => {
      window.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerleave', onLeave);
      scroller.removeEventListener('scroll', kick);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [ref, scrollRef]);
}

/** The ink header band: a dot grid and two light blooms at different depths.
 *  `fadeOnScroll` lifts and fades the content as the page scrolls past it; turn
 *  it off for a band that stays on screen (a panel header). */
export function ParallaxBand({ children, className = '', scrollRef, fadeOnScroll = true }: {
  children: React.ReactNode;
  className?: string;
  scrollRef?: React.RefObject<HTMLElement>;
  fadeOnScroll?: boolean;
}) {
  const ref = useRef<HTMLElement>(null);
  useParallax(ref, scrollRef);
  return (
    <section ref={ref} className={`as-hero ${className}`}>
      <div className="as-layer as-layer-grid" aria-hidden />
      <div className="as-layer as-layer-glow-a" aria-hidden />
      <div className="as-layer as-layer-glow-b" aria-hidden />
      <div className={`${fadeOnScroll ? 'as-hero-copy ' : ''}relative`}>{children}</div>
    </section>
  );
}

/**
 * A segmented control whose highlight slides to the selected option.
 * Arrow keys move the selection, as in a native radio group.
 */
export function SlidingSegments<T extends string>({ value, options, onChange, size = 'md', ariaLabel, labelledBy }: {
  value: T;
  options: { value: T; label: React.ReactNode }[];
  onChange: (v: T) => void;
  size?: 'sm' | 'md';
  ariaLabel?: string;
  labelledBy?: string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [box, setBox] = useState<{ x: number; w: number } | null>(null);

  const measure = useCallback(() => {
    const el = refs.current[value];
    if (el) setBox({ x: el.offsetLeft, w: el.offsetWidth });
  }, [value]);

  useLayoutEffect(() => {
    measure();
    // Keep the selected option visible when the row scrolls sideways (narrow
    // screens). Only the row's own container moves: scrollIntoView would also
    // scroll the page to every toggle on it.
    const el = refs.current[value];
    const track = trackRef.current;
    const scroller = track?.parentElement;
    if (!el || !track || !scroller || scroller.scrollWidth <= scroller.clientWidth) return;
    const left = track.offsetLeft + el.offsetLeft;
    const right = left + el.offsetWidth;
    if (left < scroller.scrollLeft) scroller.scrollLeft = left - 8;
    else if (right > scroller.scrollLeft + scroller.clientWidth) scroller.scrollLeft = right - scroller.clientWidth + 8;
  }, [measure, value]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(track);
    return () => ro.disconnect();
  }, [measure]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const i = options.findIndex((o) => o.value === value);
    const next = options[(i + (e.key === 'ArrowRight' ? 1 : -1) + options.length) % options.length];
    onChange(next.value);
    refs.current[next.value]?.focus();
  };

  const sm = size === 'sm';
  return (
    <div
      ref={trackRef}
      role="radiogroup"
      aria-label={ariaLabel}
      aria-labelledby={labelledBy}
      onKeyDown={onKeyDown}
      className={`relative inline-flex items-center gap-0.5 bg-slate-100 ${sm ? 'p-0.5 rounded-lg' : 'p-1 rounded-xl'}`}
    >
      <span
        aria-hidden
        className={`as-seg-indicator absolute left-0 bg-white shadow-[0_1px_3px_rgba(11,19,43,0.12),0_1px_1px_rgba(11,19,43,0.04)] ${
          sm ? 'top-0.5 bottom-0.5 rounded-md' : 'top-1 bottom-1 rounded-lg'
        }`}
        style={{ width: box?.w ?? 0, transform: `translate3d(${box?.x ?? 0}px,0,0)`, opacity: box ? 1 : 0 }}
      />
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            ref={(el) => { refs.current[o.value] = el; }}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(o.value)}
            className={`relative z-10 font-bold whitespace-nowrap tabular-nums transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0096D6]/50 ${
              sm ? 'px-2.5 py-1 rounded-md text-[11px]' : 'px-3 py-1.5 rounded-lg text-xs'
            } ${active ? 'text-[#0B132B]' : 'text-slate-500 hover:text-slate-800'}`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** A number that eases from its previous value to the new one. */
export function useCountUp(target: number, duration = 900): number {
  // Starts from zero (the value is fetched, never server-rendered), so the
  // first frame is not the final number followed by a jump back to 0.
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? target : 0));
  const from = useRef(0);
  useEffect(() => {
    if (prefersReducedMotion() || !Number.isFinite(target)) {
      setShown(target);
      from.current = target;
      return;
    }
    const start = performance.now();
    const origin = from.current;
    let raf = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(2, -10 * t); // exponential ease-out
      const v = t >= 1 ? target : origin + (target - origin) * eased;
      setShown(v);
      from.current = v;
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return Number.isInteger(target) ? Math.round(shown) : shown;
}

export function CountUp({ value }: { value: number }) {
  return <>{useCountUp(value).toLocaleString()}</>;
}

/**
 * Keeps an overlay mounted through its exit animation. `closing` is true for
 * the last `exitMs` before it unmounts.
 */
export function usePresence(open: boolean, exitMs = 220): { mounted: boolean; closing: boolean } {
  const [mounted, setMounted] = useState(open);
  const [closing, setClosing] = useState(false);
  useEffect(() => {
    if (open) {
      setMounted(true);
      setClosing(false);
      return;
    }
    if (!mounted) return;
    if (prefersReducedMotion()) { setMounted(false); return; }
    setClosing(true);
    const t = window.setTimeout(() => { setMounted(false); setClosing(false); }, exitMs);
    return () => window.clearTimeout(t);
  }, [open, mounted, exitMs]);
  return { mounted, closing };
}

/**
 * Rises into place the first time it scrolls into view. Anything already on
 * screen when the page renders is left alone (its own entrance covers it), and
 * the content stays visible if IntersectionObserver is unavailable.
 */
export function Reveal({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion() || typeof IntersectionObserver === 'undefined') return;
    if (el.getBoundingClientRect().top < window.innerHeight) return;
    el.classList.add('as-reveal-pending');
    const io = new IntersectionObserver((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      el.classList.add('as-reveal-in');
      el.classList.remove('as-reveal-pending');
      io.disconnect();
    }, { rootMargin: '0px 0px -8% 0px' });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return <div ref={ref} className={className}>{children}</div>;
}
