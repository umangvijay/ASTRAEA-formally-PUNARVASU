import { notFound } from "next/navigation";
import { MODULES } from "@/lib/api";
import ModuleWorkbench from "./Workbench";

// The six registry modules are the only dynamic console routes. Everything else
// is rejected by the router itself — a real HTTP 404, not a streamed fallback
// (the root app/loading.tsx used to commit a 200 before notFound() could fire).
export const dynamicParams = false;

export function generateStaticParams() {
  return MODULES.map((m) => ({ module: m.codename }));
}

export default async function ModulePage({
  params,
}: {
  params: Promise<{ module: string }>;
}) {
  const { module: codename } = await params;
  // defense in depth: dynamicParams=false already 404s unknown slugs, but keep
  // the guard so a future registry change can never render a blank workbench.
  if (!MODULES.some((m) => m.codename === codename)) {
    notFound();
  }
  return <ModuleWorkbench codename={codename} />;
}
