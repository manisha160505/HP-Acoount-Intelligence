import Image from 'next/image';

// "Powered by BridgeAI" with the BridgeAI logo, as in the Zebra platform
// (components/brand/Brand.tsx there): the same logo files at the same sizes,
// with the label in this app's own colours. `unoptimized`: the files are
// already 273x78 and 17 KB, so they are served as they are rather than
// through Next's image resizer.
//
//   * dark (default) - inline, for light surfaces: the page footer. The label
//     is slate-500, like the secondary text on this app's light pages;
//   * light - a small caps label over the light version of the logo (white
//     mark, gold "AI"), for the navy (#0B132B) surfaces: the sign-in card and
//     the bottom of the dashboard sidebar. The label is styled like the
//     sidebar's own "Account Intelligence" caption (10px, semibold, uppercase,
//     gray-400). Left aligned, as in a sidebar; `center` for a centred card.
export default function PoweredByBridgeAI({ tone = 'dark', center = false, className = '' }:
  { tone?: 'dark' | 'light'; center?: boolean; className?: string }) {
  if (tone === 'light') {
    return (
      <span className={`flex flex-col ${center ? 'items-center' : 'items-start'} gap-1.5 ${className}`}>
        <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Powered by</span>
        <Image src="/brand/bridgeai-logo-light.png" alt="BridgeAI" width={273} height={78}
               unoptimized className="h-6 w-auto" />
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-2 text-xs text-slate-500 ${className}`}>
      Powered by
      <Image src="/brand/bridgeai-logo.png" alt="BridgeAI" width={273} height={78} unoptimized
             className="h-5 w-auto" />
    </span>
  );
}
