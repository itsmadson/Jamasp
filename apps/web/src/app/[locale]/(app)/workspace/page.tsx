import { Workspace } from "@/components/workspace/workspace";

export default async function WorkspacePage({
  params,
  searchParams,
}: PageProps<"/[locale]/workspace">) {
  const { locale } = await params;
  const { source } = await searchParams;
  return (
    <Workspace
      locale={locale}
      initialSourceId={typeof source === "string" ? source : undefined}
    />
  );
}
