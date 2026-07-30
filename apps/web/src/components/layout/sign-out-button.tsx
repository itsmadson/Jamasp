"use client";

import { LogOut } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { logout } from "@/lib/api/auth";

export function SignOutButton({ locale }: { locale: string }) {
  const t = useTranslations("auth");
  const router = useRouter();

  return (
    <button
      type="button"
      className="flex items-center gap-1.5 text-sm text-muted hover:text-foreground"
      onClick={async () => {
        await logout();
        router.replace(`/${locale}/login`);
        router.refresh();
      }}
    >
      {/* Mirrored under RTL: a door-and-arrow glyph points the wrong way otherwise. */}
      <LogOut aria-hidden size={15} className="rtl:-scale-x-100" />
      {t("signOut")}
    </button>
  );
}
