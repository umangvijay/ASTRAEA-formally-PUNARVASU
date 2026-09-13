import type { Plate } from "@/components/Lightbox";

export const PLATES: Plate[] = [
  {
    id: "medic",
    title: "MEDIC · the healer",
    caption: "Telemetry becomes a ranked hypothesis, then a patch you approve.",
    image: "/cosmos/plate-medic.png",
    href: "/docs/medic",
  },
  {
    id: "operator",
    title: "OPERATOR · the navigator",
    caption: "Searches the live web, then operates a real screen when there is no API.",
    image: "/cosmos/plate-operator.png",
    href: "/docs/operator",
  },
  {
    id: "shield",
    title: "SHIELD · the warden",
    caption: "Auth logs become an attack graph. Containment waits for you.",
    image: "/cosmos/plate-shield.png",
    href: "/docs/shield",
  },
  {
    id: "vaani",
    title: "VAANI · the voice",
    caption: "Full-duplex speech. Consent first. PII never stored raw.",
    image: "/cosmos/plate-vaani.png",
    href: "/docs/vaani",
  },
  {
    id: "forge",
    title: "FORGE · the smith",
    caption: "Failures become tools. Promotion only on a measured score.",
    image: "/cosmos/plate-forge.png",
    href: "/docs/forge",
  },
  {
    id: "astraea",
    title: "ASTRAEA · return of the light",
    caption: "Six products, one brain. Offline, then the same build on Vertex.",
    image: "/cosmos/plate-astraea.png",
    href: "/docs/architecture",
  },
];
