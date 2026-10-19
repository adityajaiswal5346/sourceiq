/**
 * DocuMind — Copyright (positioned by parent; no layout footprint).
 */

const COPYRIGHT_HOLDER = "Aditya Jaiswal";

export default function Footer({ className = "" }: { className?: string }) {
  const year = new Date().getFullYear();

  return (
    <footer
      role="contentinfo"
      className={`pointer-events-none select-none ${className}`.trim()}
    >
      <p className="text-2xs text-ink-disabled whitespace-nowrap">
        © {year} {COPYRIGHT_HOLDER}. All rights reserved.
      </p>
    </footer>
  );
}
