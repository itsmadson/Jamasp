import { setRequestLocale } from "next-intl/server";

import { AskScreen } from "@/components/query/ask-screen";

export default async function AskPage({ params }: PageProps<"/[locale]/sources/[id]/ask">) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <AskScreen locale={locale} sourceId={id} />;
}
