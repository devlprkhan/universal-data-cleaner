(() => {
  const labelCopyButtons = () => {
    document.querySelectorAll(".md-code__button").forEach((button) => {
      if (!button.hasAttribute("aria-label")) {
        button.setAttribute("aria-label", "Copy code to clipboard");
      }
    });
  };

  const labelIconLinks = () => {
    document.querySelectorAll(".md-content__button[title]").forEach((link) => {
      if (!link.hasAttribute("aria-label")) {
        link.setAttribute("aria-label", link.getAttribute("title"));
      }
    });
  };

  const enableScrollableTables = () => {
    document.querySelectorAll(".md-typeset__scrollwrap").forEach((wrap) => {
      if (wrap.scrollWidth > wrap.clientWidth + 1) {
        wrap.setAttribute("tabindex", "0");
        wrap.setAttribute("role", "region");
        wrap.setAttribute("aria-label", "Scrollable table");
      } else {
        wrap.removeAttribute("tabindex");
        wrap.removeAttribute("role");
        wrap.removeAttribute("aria-label");
      }
    });
  };

  document.addEventListener("DOMContentLoaded", () => {
    labelCopyButtons();
    labelIconLinks();
    enableScrollableTables();

    const liveRegion = document.createElement("div");
    liveRegion.className = "sr-only";
    liveRegion.setAttribute("aria-live", "polite");
    liveRegion.setAttribute("aria-atomic", "true");
    document.body.appendChild(liveRegion);

    document.addEventListener("click", (event) => {
      if (!(event.target instanceof Element)) return;
      if (!event.target.closest(".md-code__button")) return;
      liveRegion.textContent = "Code copied to clipboard";
      window.setTimeout(() => {
        liveRegion.textContent = "";
      }, 2000);
    });

    const observer = new MutationObserver(() => {
      labelCopyButtons();
      labelIconLinks();
      enableScrollableTables();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    window.addEventListener("resize", enableScrollableTables);
  });
})();
