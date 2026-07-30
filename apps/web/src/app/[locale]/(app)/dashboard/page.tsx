import { Dashboard } from "@/components/dashboard/dashboard";

export default async function DashboardPage({ params }: PageProps<"/[locale]/dashboard">) {
  const { locale } = await params;
  return <Dashboard locale={locale} />;
}
