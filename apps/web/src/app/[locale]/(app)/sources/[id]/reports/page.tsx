import { setRequestLocale } from "next-intl/server";

import { ReportBuilder } from "@/components/report/report-builder";

export default async function ReportsPage({
  params,
}: PageProps<"/[locale]/sources/[id]/reports">) {
  const { locale, id } = await params;
  setRequestLocale(locale);

  return <ReportBuilder locale={locale} sourceId={id} />;
}
