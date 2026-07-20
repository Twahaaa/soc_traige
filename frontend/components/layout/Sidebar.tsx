"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

// Dashboard is the only real route in scope; the design's Timeline/Analytics
// nav entries are dropped because the backend exposes no endpoint for them.
const NAV_ITEMS = [
  { href: "/dashboard", label: "Alerts", short: "ALT" },
] as const;

export default function Sidebar() {
  const path = usePathname();

  return (
    <aside className="w-14 flex-shrink-0 bg-surface-secondary border-r border-surface-tertiary flex flex-col items-center py-3 gap-1">
      {/* Logo */}
      <div className="w-9 h-9 bg-critical rounded-xl flex items-center justify-center mb-3 flex-shrink-0 shadow-sm">
        <span className="text-white font-bold text-[11px] tracking-tight font-mono">SOC</span>
      </div>

      {/* Nav items */}
      {NAV_ITEMS.map((item) => {
        const active = path === item.href || (path?.startsWith(item.href + "/") ?? false);
        return (
          <Link
            key={item.href}
            href={item.href}
            title={item.label}
            className={cn(
              "w-10 h-10 rounded-xl flex flex-col items-center justify-center relative transition-all gap-0.5",
              active ? "bg-critical-bg" : "hover:bg-surface",
            )}
          >
            <span
              className={cn(
                "font-mono text-[9px] font-bold tracking-widest leading-none",
                active ? "text-critical" : "text-gray-400",
              )}
            >
              {item.short}
            </span>
            {active && <div className="w-1 h-1 rounded-full bg-critical" />}
          </Link>
        );
      })}

      {/* Divider */}
      <div className="w-6 h-px bg-surface-tertiary my-1" />

      {/* Help */}
      <div className="mt-auto">
        <button
          title="Help"
          className="w-10 h-10 rounded-xl flex items-center justify-center hover:bg-surface transition-all"
        >
          <span className="font-mono text-[9px] font-bold tracking-widest text-gray-400">HLP</span>
        </button>
      </div>
    </aside>
  );
}