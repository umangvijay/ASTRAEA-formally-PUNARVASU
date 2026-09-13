"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Vault lives under Settings — keep the old URL from 404ing as a fake module. */
export default function VaultRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/console/settings?tab=vault"); }, [router]);
  return <p className="label">opening vault…</p>;
}
