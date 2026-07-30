import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { LocaleSwitcher } from "./locale-switcher";
import { NavLink } from "./nav-link";
import { SignOutButton } from "./sign-out-button";

export async function AppShell({
  locale,
  children,
}: {
  locale: string;
  children: React.ReactNode;
}) {
  const nav = await getTranslations("nav");
  const app = await getTranslations("app");

  // Ordered the way the work is actually done: see the state, do the work, then
  // manage what it runs against.
  const links = [
    { href: `/${locale}/dashboard`, label: nav("dashboard") },
    { href: `/${locale}/workspace`, label: nav("workspace") },
    { href: `/${locale}/sources`, label: nav("sources") },
    { href: `/${locale}/settings`, label: nav("settings") },
  ];

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-border bg-background/85 px-6 py-2.5 backdrop-blur">
        <div className="flex items-center gap-7">
          <Link
            href={`/${locale}/dashboard`}
            className="flex items-baseline gap-2 text-lg font-bold tracking-tight"
          >
            {app("name")}
            <span className="text-[10px] font-normal text-muted">{app("tagline")}</span>
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            {links.map((link) => (
              <NavLink key={link.href} href={link.href}>
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <LocaleSwitcher locale={locale} />
          <SignOutButton locale={locale} />
        </div>
      </header>
      <main className="flex-1 px-6 py-6">{children}</main>
    </div>
  );
}
