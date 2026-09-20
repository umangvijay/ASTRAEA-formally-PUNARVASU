import type { Metadata, Viewport } from "next";
import { Space_Grotesk, JetBrains_Mono, Fraunces } from "next/font/google";
import { CosmosBackdrop } from "@/components/CosmosBackdrop";
import "./globals.css";

const display = Space_Grotesk({
  subsets: ["latin"], weight: ["400", "500", "700"], variable: "--font-display-load",
});
const serif = Fraunces({
  subsets: ["latin"], weight: ["400", "600", "700"], variable: "--font-serif-load",
});
const mono = JetBrains_Mono({
  subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-mono-load",
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export const metadata: Metadata = {
  title: "Astraea — control plane for autonomous agents",
  description:
    "Lab control plane for six agents with one SENTINEL brain. AI SRE, computer-use, SOC, voice, self-evolving skills and a SQL model — usable solo or fused.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning data-scroll-behavior="smooth">
      <head>
        <script dangerouslySetInnerHTML={{ __html: `
          try {
            const t = localStorage.getItem("astraea-theme") || "dark";
            document.documentElement.dataset.theme = t;
          } catch(e) {}
        `}} />
      </head>
      <body className={`${display.variable} ${serif.variable} ${mono.variable}`}>
        <CosmosBackdrop />
        {children}
      </body>
    </html>
  );
}
