"use client";

import { useEffect, useState } from "react";

export function useTheme() {
  const [theme, setTheme] = useState<string>("dark");
  useEffect(() => {
    const t = window.localStorage.getItem("astraea-theme") ?? "dark";
    document.documentElement.dataset.theme = t;
    setTheme(t);
  }, []);
  const toggle = () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("astraea-theme", next);
    setTheme(next);
  };
  return { theme, toggle };
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button className="theme-toggle" onClick={toggle} aria-label="toggle theme">
      {theme === "dark" ? "+ Day" : "+ Night"}
    </button>
  );
}
