import { PublicNav } from "@/components/PublicNav";
import { DocsNav } from "@/components/DocsNav";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PublicNav />
      <div className="docs-shell">
        <DocsNav />
        <main className="docs-main" id="docs-content">{children}</main>
      </div>
    </>
  );
}
