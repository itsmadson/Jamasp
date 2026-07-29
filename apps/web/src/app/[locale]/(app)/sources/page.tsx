import { setRequestLocale } from "next-intl/server";

import { SourceList } from "@/components/sources/source-list";

export default async function SourcesPage({ params }: PageProps<"/[locale]/sources">) {
  const { locale } = await params;
  setRequestLocale(locale);

  // Loaded client-side so the browser attaches the httpOnly session cookie;
  // a server-side fetch would have to forward it by hand.
  return <SourceList locale={locale} />;
}
