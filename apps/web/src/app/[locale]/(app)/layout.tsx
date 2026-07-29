import { setRequestLocale } from "next-intl/server";

import { AppShell } from "@/components/layout/app-shell";

export default async function AppLayout({ children, params }: LayoutProps<"/[locale]">) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <AppShell locale={locale}>{children}</AppShell>;
}
