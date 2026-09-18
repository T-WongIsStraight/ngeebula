// Light / dark switch, fixed in the top-right corner.
// The knob is a little train that slides along a track when you flip it.

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* storage may be unavailable */ }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("theme", theme); } catch { /* ignore */ }
  }, [theme]);

  const light = theme === "light";
  return (
    <button
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
            <rect x="7" y="7" width="7" height="6" rx="1" fill="var(--bg)" opacity=".9" />
            <rect x="17" y="7" width="7" height="6" rx="1" fill="var(--bg)" opacity=".9" />
            <rect x="27" y="7" width="7" height="6" rx="1" fill="var(--bg)" opacity=".9" />
          </svg>
        </span>
      </span>
    </button>
  );
}
