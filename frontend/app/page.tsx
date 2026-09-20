"use client";

import dynamic from "next/dynamic";
import { PublicNav } from "@/components/PublicNav";

// the 3D scene is heavy (three.js + textures) — load it lazily so the page
// paints instantly and the sky fades in when the scene is ready
const SolarSystem3D = dynamic(
  () => import("@/components/SolarSystem3D").then((m) => m.SolarSystem3D),
  {
    ssr: false,
    loading: () => (
      <div
        aria-hidden
        style={{ position: "fixed", inset: 0, background: "var(--paper)", transition: "opacity .6s" }}
      />
    ),
  },
);

export default function Home() {
  return (
    <main className="home-stage">
      <SolarSystem3D />
      <PublicNav />
    </main>
  );
}
