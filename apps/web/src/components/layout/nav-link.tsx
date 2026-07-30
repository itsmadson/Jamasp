"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * A nav item that shows where you are.
 *
 * usePathname is a client hook by design — the server cannot read the current URL,
 * so this is the smallest possible client boundary rather than making the whole
 * shell a client component.
 */
export function NavLink({
  href,
  icon,
  children,
}: {
  href: string;
  /**
   * A rendered element, not a component. The shell is a server component, and a
   * function cannot cross that boundary — only its output can.
   */
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(`${href}/`);

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={
        active
          ? "flex items-center gap-2 rounded-lg bg-surface px-3 py-1.5 font-medium text-foreground"
          : "flex items-center gap-2 rounded-lg px-3 py-1.5 text-muted transition-colors hover:text-foreground"
      }
    >
      {/* Decorative: the label beside it already names the destination. */}
      {icon}
      {children}
    </Link>
  );
}
