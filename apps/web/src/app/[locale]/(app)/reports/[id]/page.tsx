import { setRequestLocale } from "next-intl/server";

import { SavedReport } from "@/components/report/saved-report";

export default async function ReportPage({ params }: PageProps<"/[locale]/reports/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <SavedReport locale={locale} reportId={id} />;
}
