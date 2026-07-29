import { setRequestLocale } from "next-intl/server";

import { ReviewScreen } from "@/components/review/review-screen";

export default async function ReviewPage({
  params,
}: PageProps<"/[locale]/sources/[id]/review">) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <ReviewScreen locale={locale} sourceId={id} />;
}
