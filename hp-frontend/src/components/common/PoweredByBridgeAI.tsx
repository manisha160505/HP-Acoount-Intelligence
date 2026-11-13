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
//
// `subtitle` is a one-line light version for the navy Navbar: "Powered by"
// and the logo on one row, set directly under "Account Intelligence" like a
// product subtitle. It adds no width to the Navbar, so it stays on screen on
// every page after sign-in at any window size (client, 12 Nov: the footer and
// the sidebar bottom were out of sight).
export default function PoweredByBridgeAI({ tone = 'dark', center = false, subtitle = false, className = '' }:
  { tone?: 'dark' | 'light'; center?: boolean; subtitle?: boolean; className?: string }) {
  if (tone === 'light' && subtitle) {
    return (
      <span className={`inline-flex items-center gap-1.5 ${className}`}>
        <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 whitespace-nowrap leading-none">Powered by</span>
        <Image src="/brand/bridgeai-logo-light.png" alt="BridgeAI" width={273} height={78}
               unoptimized className="h-6 w-auto" />
      </span>
    );
  }
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
    <span className={`inline-flex items-center gap-2 text-[13px] text-slate-500 ${className}`}>
      Powered by
      <Image src="/brand/bridgeai-logo.png" alt="BridgeAI" width={273} height={78} unoptimized
             className="h-7 w-auto" />
    </span>
  );
}
