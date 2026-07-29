import { setRequestLocale } from "next-intl/server";

import { SourceDetail } from "@/components/sources/source-detail";

export default async function SourcePage({ params }: PageProps<"/[locale]/sources/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <SourceDetail locale={locale} sourceId={id} />;
}
