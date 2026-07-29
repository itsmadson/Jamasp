import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { LocaleSwitcher } from "./locale-switcher";
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

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between border-b border-border px-6 py-3">
        <div className="flex items-center gap-8">
          <Link href={`/${locale}/sources`} className="text-lg font-bold tracking-tight">
            {app("name")}
          </Link>
          <nav className="flex items-center gap-5 text-sm">
            <Link href={`/${locale}/sources`} className="text-muted hover:text-foreground">
              {nav("sources")}
            </Link>
            <Link href={`/${locale}/settings`} className="text-muted hover:text-foreground">
              {nav("settings")}
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <LocaleSwitcher locale={locale} />
          <SignOutButton locale={locale} />
        </div>
      </header>
      <main className="flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
