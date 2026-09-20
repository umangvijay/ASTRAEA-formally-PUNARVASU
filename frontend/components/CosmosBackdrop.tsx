"use client";

/**
 * Ambient observatory sky behind every page. The home page renders its own
 * full SolarSystem3D scene and is skipped here — inner pages get the same
 * cosmos theme (milky way, nebulas, star layers, comets) without the
 * interactive scene weight, so content stays readable.
 */
import { usePathname } from "next/navigation";
import { Cosmos } from "./Cosmos";

export function CosmosBackdrop() {
  const pathname = usePathname();
  if (pathname === "/") return null;
  return <Cosmos ambient />;
}
