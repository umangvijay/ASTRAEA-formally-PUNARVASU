import { notFound } from "next/navigation";
import { MODULES } from "@/lib/api";
import ModuleWorkbench from "./Workbench";

export default async function ModulePage({
  params,
}: {
  params: Promise<{ module: string }>;
}) {
  const { module: codename } = await params;
  if (!MODULES.some((m) => m.codename === codename)) {
    notFound();
  }
  return <ModuleWorkbench codename={codename} />;
}
