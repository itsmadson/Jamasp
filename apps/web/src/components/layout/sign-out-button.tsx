"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { logout } from "@/lib/api/auth";

export function SignOutButton({ locale }: { locale: string }) {
  const t = useTranslations("auth");
  const router = useRouter();

  return (
    <button
      type="button"
      className="text-sm text-muted hover:text-foreground"
      onClick={async () => {
        await logout();
        router.replace(`/${locale}/login`);
        router.refresh();
      }}
    >
      {t("signOut")}
    </button>
  );
}
