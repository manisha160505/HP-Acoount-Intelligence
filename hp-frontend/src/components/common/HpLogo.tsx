// The HP logo, as HP publishes it.
//
// The mark is the vector HP's own site header draws (www.hp.com, the
// `digitnav-logo-icon` symbol). The vector files on HP Brand Central sit
// behind an HP sign-in, so the public mark is used rather than redrawn.
//
// HP brand guidelines (Brand Central, "Our visual identity"):
//   * the logo is only ever Electric Blue (#024AD8) - "there can only be one blue";
//   * on a dark background or image it carries a white keyline, 8% larger
//     than the blue circle; on white the keyline disappears, so it is omitted;
//   * the minimum size is 36px.

const ELECTRIC_BLUE = '#024AD8';
const MIN_SIZE = 36;

const MARK = 'M16.04 0 12.6 9.65h2.34c1.69 0 2.4 1.33 1.87 2.82l-3.42 9.6H9.95L13.7 11.5h-1.77L8.17 22.07H4.7L12.43.4a16 16 0 0 0-.33 31.12L19.9 9.6h5.66c1.17 0 2.64.79 2 2.58l-3.17 8.97c-.4 1.14-1.37 1.37-2.14 1.37h-3.48L15.4 32l.6.01a16 16 0 0 0 .04-32Zm6.67 11.48-3.28 9.2h1.74l3.28-9.2h-1.74Z';

// The keyline circle is 8% larger than the 16-unit blue circle.
const KEYLINE_R = 16 * 1.08;
const PAD = KEYLINE_R - 16;

export default function HpLogo({ size = MIN_SIZE, onDark = false, className = '' }:
  { size?: number; onDark?: boolean; className?: string }) {
  const px = Math.max(size, MIN_SIZE);
  // With the keyline the drawing is wider than the mark, so the view box grows
  // to hold it and the blue circle stays the same size on screen.
  const viewBox = onDark
    ? `${-PAD} ${-PAD} ${32 + 2 * PAD} ${32 + 2 * PAD}`
    : '0 0 32 32';
  return (
    <svg
      role="img"
      aria-label="HP"
      viewBox={viewBox}
      width={px}
      height={px}
      className={`flex-shrink-0 ${className}`}
    >
      {onDark && <circle cx="16" cy="16" r={KEYLINE_R} fill="#FFFFFF" />}
      <path d={MARK} fill={ELECTRIC_BLUE} />
    </svg>
  );
}
