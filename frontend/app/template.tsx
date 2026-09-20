/**
 * Route transition: remounts on every navigation, giving each page a soft
 * fade-in entrance. Opacity-only — never transform — so position:fixed
 * chrome (nav, dock) inside pages keeps its containing block.
 */
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
