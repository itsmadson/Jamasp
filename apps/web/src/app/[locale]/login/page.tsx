import Image from "next/image";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { LoginPanel } from "@/components/auth/login-panel";

export default async function LoginPage({ params }: PageProps<"/[locale]/login">) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("auth");
  const app = await getTranslations("app");

  return (
    <main className="grid min-h-dvh place-items-center px-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3">
          <Image src="/logo.png" alt="" width={52} height={52} preload />
          <h1 className="text-3xl font-bold tracking-tight">{app("name")}</h1>
        </div>
        <h2 className="mb-1 text-lg font-medium">{t("title")}</h2>
        <p className="mb-6 text-sm text-muted">{t("subtitle")}</p>
        <LoginPanel locale={locale} />
      </div>
    </main>
  );
}
