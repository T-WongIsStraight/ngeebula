// Light / dark switch, fixed in the top-right corner. The knob is a little
// train that slides between "Night" and "Day". The choice is remembered in
// localStorage; the first visit follows the operating system.

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

export const THEME_KEY = "tas-theme";

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* private mode or blocked storage: fall through */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0f1115" : "#f1f4f8");
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  const light = theme === "light";
  return (
    <button
      type="button"
      className={"theme-toggle " + theme}
      onClick={() => setTheme(light ? "dark" : "light")}
      aria-label={light ? "Switch to dark mode" : "Switch to light mode"}
      title={light ? "Switch to dark mode" : "Switch to light mode"}
    >
      <span className="tt-track">
        <span className="tt-station left">Night</span>
        <span className="tt-station right">Day</span>
        <span className="tt-knob" aria-hidden="true">
          <svg viewBox="0 0 40 20" width="34" height="17">
            <rect x="2" y="3" width="36" height="14" rx="4" fill="currentColor" />
            <rect x="7" y="7" width="7" height="6" rx="1" fill="var(--surface)" opacity=".9" />
            <rect x="17" y="7" width="7" height="6" rx="1" fill="var(--surface)" opacity=".9" />
            <rect x="27" y="7" width="7" height="6" rx="1" fill="var(--surface)" opacity=".9" />
          </svg>
        </span>
      </span>
    </button>
  );
}
