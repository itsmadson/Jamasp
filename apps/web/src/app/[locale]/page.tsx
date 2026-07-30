import { redirect } from "next/navigation";

export default async function LocaleIndex({ params }: PageProps<"/[locale]">) {
  const { locale } = await params;
  redirect(`/${locale}/dashboard`);
}
