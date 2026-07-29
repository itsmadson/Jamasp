import { setRequestLocale } from "next-intl/server";

import { SettingsScreen } from "@/components/settings/settings-screen";

export default async function SettingsPage({ params }: PageProps<"/[locale]/settings">) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <SettingsScreen />;
}
