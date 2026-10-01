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

/**
 * One clock for every "grows to its value" animation. Bars and rings run it in
 * CSS (--as-count-ms / --as-ease-count in globals.css); numbers run it here.
 * Same length, same curve, same start delay - so a bar and the number beside
 * it arrive together.
 */
export const COUNT_MS = 1000;
/** easeOutExpo, the curve CSS approximates with cubic-bezier(0.19, 1, 0.22, 1). */
const easeOutExpo = (t: number) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
/** The start delay for item `i` in a staggered set of bars. Set it as the
 *  bar's --as-d and pass the same number to the CountUpText beside it. */
export const growDelay = (i: number, base = 120, step = 30, cap = 12) => base + Math.min(i, cap) * step;

/** A number that eases from its previous value to the new one. */
export function useCountUp(target: number, duration = COUNT_MS, delay = 0): number {
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
    const start = performance.now() + delay;
    const origin = from.current;
    let raf = 0;
    const step = (now: number) => {
      const t = Math.max(0, Math.min(1, (now - start) / duration));
      const v = t >= 1 ? target : origin + (target - origin) * easeOutExpo(t);
      setShown(v);
      from.current = v;
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, delay]);
  return Number.isInteger(target) ? Math.round(shown) : shown;
}

export function CountUp({ value, delay = 0 }: { value: number; delay?: number }) {
  return <>{useCountUp(value, COUNT_MS, delay).toLocaleString()}</>;
}

/** A ring that fills to `value` of `max` on the shared clock - for a score
 *  shown as a number inside a circle. */
export function ScoreRing({ value, max = 100, size = 96, stroke = 4, className = '', trackClassName = '' }: {
  value: number; max?: number; size?: number; stroke?: number; className?: string; trackClassName?: string;
}) {
  const r = (size - stroke) / 2;
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="absolute inset-0 -rotate-90" aria-hidden>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className={trackClassName} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} strokeLinecap="round"
        pathLength={100} strokeDasharray="100" strokeDashoffset={100 - pct}
        className={`as-ring ${className}`}
      />
    </svg>
  );
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

/**
 * A page header band: title, subtitle and actions on the ink band, with the
 * page's first card meant to overlap its lower edge (give the content that
 * follows a negative top margin).
 */
export function PageHero({ title, subtitle, actions, width = 'max-w-7xl', children }: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  width?: string;
  children?: React.ReactNode;
}) {
  return (
    <ParallaxBand>
      <div className={`${width} mx-auto px-4 sm:px-6 lg:px-8 pt-10 pb-20 sm:pt-12 sm:pb-24`}>
        {children}
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div className="min-w-0">
            <h1 className="as-rise text-2xl sm:text-3xl font-extrabold text-white tracking-tight [text-wrap:balance]">{title}</h1>
            {subtitle && (
              <p className="as-rise mt-2 text-sm text-slate-300/90 max-w-2xl" style={{ ['--as-delay' as string]: '70ms' }}>{subtitle}</p>
            )}
          </div>
          {actions && (
            <div className="as-rise flex items-center gap-2 flex-shrink-0" style={{ ['--as-delay' as string]: '110ms' }}>{actions}</div>
          )}
        </div>
      </div>
    </ParallaxBand>
  );
}

// One number inside display text: "10001+", "IDR 32,769 billion", "1,250".
const NUMBER_TOKEN = /\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?/g;

/**
 * Counts the one number in `text` up from zero, keeping its prefix, suffix,
 * thousands separators and decimal places, and ends on `text` exactly - the
 * final frame is the original string, never a reformatted one. Text with no
 * number, or more than one ("10B-100B", "2023 vs 2024"), renders unchanged.
 */
export function CountUpText({ text, duration = COUNT_MS, delay = 0, first = false }: {
  text: string | number | null | undefined;
  duration?: number;
  /** ms before counting starts - match the bar's --as-d. */
  delay?: number;
  /** Count the first number even when more follow, for "18/20" or "64/100". */
  first?: boolean;
}) {
  const str = text == null ? '' : String(text);
  const matches = str.match(NUMBER_TOKEN) ?? [];
  const token = matches.length === 1 || (first && matches.length > 0) ? matches[0] : null;
  const target = token ? Number(token.replace(/,/g, '')) : NaN;
  const shown = useCountUp(Number.isFinite(target) ? target : 0, duration, delay);
  if (!token || !Number.isFinite(target) || shown === target) return <>{str}</>;

  const at = str.indexOf(token);
  const decimals = token.includes('.') ? token.split('.')[1].length : 0;
  const grouped = token.includes(',');
  const value = Math.min(shown, target).toLocaleString('en-US', {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: grouped,
  });
  return (
    <span aria-label={str}>
      <span aria-hidden>{str.slice(0, at)}{value}{str.slice(at + token.length)}</span>
    </span>
  );
}
