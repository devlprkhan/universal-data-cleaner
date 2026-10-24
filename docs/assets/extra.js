(() => {
  const labelCopyButtons = () => {
    document.querySelectorAll(".md-code__button").forEach((button) => {
      if (button.classList.contains("is-copied")) return;
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

    let copyStateTimer;

    const resetCopyButton = (button) => {
      window.clearTimeout(button.copyLabelTimer);
      button.copyLabelTimer = undefined;
      button.classList.remove("is-copied");
      button.setAttribute("aria-label", "Copy code to clipboard");
      button.setAttribute("title", "Copy to clipboard");
      if (button.copyTooltip) {
        button.copyTooltip.textContent = "Copy to clipboard";
        button.copyTooltip = undefined;
      }
      if (button.copyTooltipHost) {
        button.copyTooltipHost.classList.remove("udc-copied-tooltip");
        button.copyTooltipHost = undefined;
      }
    };

    document.addEventListener("click", (event) => {
      if (!(event.target instanceof Element)) return;
      const button = event.target.closest(
        '.md-code__button[data-md-type="copy"]',
      );
      if (!button) return;

      document
        .querySelectorAll(".md-code__button.is-copied")
        .forEach((other) => {
          if (other !== button) resetCopyButton(other);
        });

      window.clearTimeout(button.copyLabelTimer);
      button.classList.add("is-copied");
      button.setAttribute("aria-label", "Copied to clipboard");
      button.setAttribute("title", "Copied to clipboard");

      const tooltipId = button.getAttribute("aria-describedby");
      const tooltip = tooltipId ? document.getElementById(tooltipId) : null;
      button.copyTooltip = tooltip?.querySelector(".md-tooltip2__inner") ?? null;
      button.copyTooltipHost = tooltip;
      if (button.copyTooltip) {
        button.copyTooltip.textContent = "Copied to clipboard";
      }
      if (button.copyTooltipHost) {
        button.copyTooltipHost.classList.add("udc-copied-tooltip");
      }

      document.body.classList.add("udc-inline-copy");
      liveRegion.textContent = "Code copied to clipboard";

      window.clearTimeout(copyStateTimer);
      copyStateTimer = window.setTimeout(() => {
        document.body.classList.remove("udc-inline-copy");
      }, 3000);

      button.copyLabelTimer = window.setTimeout(() => {
        resetCopyButton(button);
        liveRegion.textContent = "";
      }, 1800);
    });

    const copyText = async (text) => {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
      }

      const field = document.createElement("textarea");
      field.value = text;
      field.setAttribute("readonly", "");
      field.style.position = "fixed";
      field.style.opacity = "0";
      document.body.appendChild(field);
      field.select();
      document.execCommand("copy");
      field.remove();
    };

    document.addEventListener("click", async (event) => {
      if (!(event.target instanceof Element)) return;
      const button = event.target.closest(".hero__install-copy");
      const install = button?.closest(".hero__install");
      const text = install?.getAttribute("data-copy-text");
      if (!button || !text) return;

      try {
        await copyText(text);
      } catch {
        return;
      }

      button.classList.add("is-copied");
      button.textContent = "Copied";
      button.setAttribute("aria-label", "Install command copied");
      liveRegion.textContent = "Install command copied to clipboard";

      window.clearTimeout(button.copyTimer);
      button.copyTimer = window.setTimeout(() => {
        button.classList.remove("is-copied");
        button.textContent = "Copy";
        button.setAttribute("aria-label", "Copy install command");
        liveRegion.textContent = "";
      }, 1800);
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
