(() => {
  const surfaceSelector = [
    ".hero-panel", ".panel", ".metric-card", ".rd-card", ".source-card",
    ".review-pane", ".review-card", ".review-pilot-panel", ".review-batch-panel",
    ".review-quality-panel", ".alert-card", ".admin-metric", ".validation-metric",
    ".user-row", ".schedule-row", ".table-panel"
  ].join(",");

  const point = (surface, clientX, clientY) => {
    const rect = surface.getBoundingClientRect();
    surface.style.setProperty("--spot-x", `${clientX - rect.left}px`);
    surface.style.setProperty("--spot-y", `${clientY - rect.top}px`);
  };

  document.addEventListener("pointerover", (event) => {
    const surface = event.target.closest?.(surfaceSelector);
    if (!surface || surface.contains(event.relatedTarget)) return;
    surface.classList.add("ui-glow");
  }, { passive: true });

  document.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch") return;
    const surface = event.target.closest?.(surfaceSelector);
    if (surface) point(surface, event.clientX, event.clientY);
  }, { passive: true });

  document.addEventListener("focusin", (event) => {
    const surface = event.target.closest?.(surfaceSelector);
    if (surface) surface.classList.add("ui-glow");
  });

  document.addEventListener("pointerdown", (event) => {
    if (event.pointerType !== "touch") return;
    const surface = event.target.closest?.(surfaceSelector);
    if (!surface) return;
    point(surface, event.clientX, event.clientY);
    surface.classList.add("ui-glow");
  }, { passive: true });

  const views = document.querySelectorAll(".page-view");
  views.forEach((view) => {
    let wasVisible = view.classList.contains("visible");
    const observer = new MutationObserver(() => {
      const isVisible = view.classList.contains("visible");
      if (isVisible && !wasVisible) {
        view.classList.remove("ui-enter");
        requestAnimationFrame(() => view.classList.add("ui-enter"));
      }
      wasVisible = isVisible;
    });
    observer.observe(view, { attributes: true, attributeFilter: ["class"] });
  });
})();
