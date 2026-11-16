(() => {
  const root = document.documentElement;
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let preference;
  try {
    const stored = localStorage.getItem("citesync-theme");
    if (stored === "light" || stored === "dark") preference = stored;
  } catch {
    // Storage can be disabled; theme changes still work for this page.
  }

  function apply() {
    const theme = preference || (system.matches ? "dark" : "light");
    root.dataset.theme = theme;
    const toggle = document.querySelector(".theme-toggle");
    if (toggle) {
      const label = `Switch to ${theme === "dark" ? "light" : "dark"} theme`;
      toggle.setAttribute("aria-label", label);
      toggle.title = label;
      toggle.querySelector(".theme-moon").toggleAttribute("hidden", theme === "dark");
      toggle.querySelector(".theme-sun").toggleAttribute("hidden", theme === "light");
      toggle.hidden = false;
    }
    for (const meta of document.querySelectorAll('meta[name="theme-color"]')) {
      meta.removeAttribute("media");
      meta.content = theme === "dark" ? "#101e1a" : "#eef5f0";
    }
  }

  apply();
  system.addEventListener("change", apply);
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document.querySelector(".theme-toggle")?.addEventListener("click", () => {
      preference = root.dataset.theme === "dark" ? "light" : "dark";
      try {
        localStorage.setItem("citesync-theme", preference);
      } catch {
        // Keep the current-page choice when saving is blocked.
      }
      apply();
    });
  });
})();
