"use client";

import { usePathname, useRouter } from "next/navigation";

import { routing, type Locale } from "@/i18n/routing";
import { cn } from "@/lib/cn";

const LABELS: Record<Locale, string> = { fa: "فارسی", en: "English" };

export function LocaleSwitcher({ locale }: { locale: string }) {
  const pathname = usePathname();
  const router = useRouter();

  function switchTo(next: Locale) {
    // Swap only the locale segment so the user stays on the screen they were on.
    const segments = pathname.split("/");
    segments[1] = next;
    router.replace(segments.join("/") || `/${next}`);
  }

  return (
    <div className="flex items-center gap-1 text-sm">
      {routing.locales.map((value) => (
        <button
          key={value}
          type="button"
          onClick={() => switchTo(value)}
          aria-current={value === locale ? "true" : undefined}
          className={cn(
            "rounded px-2 py-1",
            value === locale ? "bg-accent/10 text-accent" : "text-muted hover:text-foreground",
          )}
        >
          {LABELS[value]}
        </button>
      ))}
    </div>
  );
}
