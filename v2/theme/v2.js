/* Universal Data Cleaner — docs v2 client.
   Islands only: theme, copy, menus, contents spy, search. No framework. */

(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const root = document.documentElement;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  /* ───────────────────────── Theme ───────────────────────── */

  const THEME_KEY = "udc-theme";
  const THEMES = ["system", "light", "dark"];

  function readTheme() {
    try {
      const stored = localStorage.getItem(THEME_KEY);
      return THEMES.includes(stored) ? stored : "system";
    } catch {
      return "system";
    }
  }

  function applyTheme(theme) {
    if (theme === "system") {
      delete root.dataset.theme;
    } else {
      root.dataset.theme = theme;
    }
    $$("[data-theme-set]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.themeSet === theme));
    });
    /* The cycle button shows one of its three icons, and names the next theme. */
    $$("[data-theme-cycle]").forEach((button) => {
      $$("[data-slot=icon]", button).forEach((icon, index) => {
        icon.toggleAttribute("data-current", THEMES[index] === theme);
      });
      const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
      button.setAttribute("aria-label", `${theme} theme. Switch to ${next}`);
    });
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* storage may be unavailable; the choice still applies for this page */
    }
  }

  applyTheme(readTheme());

  /* Preview helper: /?theme=light|dark|system forces a theme for screenshots and reviews. */
  const forced = new URLSearchParams(location.search).get("theme");
  if (forced === "light" || forced === "dark" || forced === "system") applyTheme(forced);

  document.addEventListener("click", (event) => {
    const cycle = event.target.closest("[data-theme-cycle]");
    if (cycle) {
      const now = readTheme();
      applyTheme(THEMES[(THEMES.indexOf(now) + 1) % THEMES.length]);
      return;
    }
    const button = event.target.closest("[data-theme-set]");
    if (button) applyTheme(button.dataset.themeSet);
  });

  /* ───────────────────────── Copy ───────────────────────── */

  const strings = (() => {
    try {
      return JSON.parse($("[data-site]").dataset.strings || "{}");
    } catch {
      return {};
    }
  })();

  async function writeClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.append(field);
    field.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    field.remove();
    return ok;
  }

  function flash(button, message, restore) {
    if (!button.dataset.idleLabel) {
      button.dataset.idleLabel = button.textContent.trim();
    }
    const width = button.getBoundingClientRect().width;
    if (width) button.style.minWidth = `${Math.ceil(width)}px`;
    button.textContent = message;
    window.clearTimeout(button._flashTimer);
    button._flashTimer = window.setTimeout(() => {
      button.textContent = restore || button.dataset.idleLabel;
      button.style.minWidth = "";
    }, 1400);
  }

  /** The text a Copy button puts on the clipboard, per frame variant. */
  function codeText(button) {
    const frame = button.closest('[data-component="code-frame"]');
    if (frame) return frameText(frame);
    const tabs = button.closest('[data-component="code-tabs"]');
    if (tabs) {
      const panel = $('[role="tabpanel"]:not([hidden])', tabs);
      const frame = panel && $('[data-component="code-frame"]', panel);
      return frame ? frameText(frame) : ($("pre code", panel)?.textContent ?? "");
    }
    return button.dataset.copyText ?? "";
  }

  function frameText(frame) {
    const variant = frame.dataset.variant;
    // A terminal session copies its commands only.
    if (variant === "terminal") {
      const commands = $$('[data-token="prompt"] [data-slot="command"]', frame).map(
        (node) => node.textContent.trim()
      );
      if (commands.length) return commands.join("\n");
    }
    // A diff copies the added and unchanged lines, without their signs.
    if (variant === "codeDiff") {
      return $$("code[data-diff]", frame)
        .filter((row) => row.dataset.diff !== "-")
        .map((row) => row.textContent.replace(/\u00a0/g, " ").trimEnd())
        .join("\n");
    }
    if (variant === "fileTree") {
      return $$("[data-tree-row]", frame)
        .map((row) => {
          const name = $('[data-slot="tree-name"]', row)?.textContent ?? "";
          return "  ".repeat(Number(row.dataset.depth) || 0) + name;
        })
        .join("\n");
    }
    return $("pre code", frame)?.textContent ?? "";
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest('[data-slot="copy"]');
    if (!button) return;
    const text = codeText(button);
    if (!text) return;
    const ok = await writeClipboard(text);
    flash(button, ok ? strings.copied || "Copied" : strings.failed || "Failed");
  });

  $$("[data-copy-markdown]").forEach((button) => {
    button.addEventListener("click", async () => {
      const href = button.dataset.md;
      const live = button.closest("[data-component=edit-link]")?.querySelector('[aria-live="polite"]');
      if (!href) return;
      try {
        const response = await fetch(href, { cache: "no-cache" });
        const text = await response.text();
        const ok = await writeClipboard(text);
        button.dataset.state = ok ? "copied" : "failed";
        if (live) live.textContent = ok ? "Copied the page as Markdown" : "Could not copy";
        window.setTimeout(() => {
          button.dataset.state = "idle";
          if (live) live.textContent = "";
        }, 1600);
      } catch {
        button.dataset.state = "failed";
        window.setTimeout(() => {
          button.dataset.state = "idle";
        }, 1600);
      }
    });
  });

  /* ───────────────────────── Disclosures ───────────────────────── */

  function setupMenu(trigger) {
    const menu = trigger.parentElement.querySelector('[data-slot="menu"]');
    if (!menu) return;
    const close = () => {
      trigger.setAttribute("aria-expanded", "false");
      menu.hidden = true;
    };
    trigger.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = trigger.getAttribute("aria-expanded") === "true";
      $$('[data-component="docs-lockup"] [data-slot="trigger"]').forEach((other) => {
        other.setAttribute("aria-expanded", "false");
        const otherMenu = other.parentElement.querySelector('[data-slot="menu"]');
        if (otherMenu) otherMenu.hidden = true;
      });
      if (!open) {
        trigger.setAttribute("aria-expanded", "true");
        menu.hidden = false;
      }
    });
    document.addEventListener("click", (event) => {
      if (!menu.hidden && !menu.contains(event.target)) close();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
    });
  }

  $$('[data-component="docs-lockup"] [data-slot="trigger"]').forEach(setupMenu);

  const sectionNav = $('[data-component="section-nav"]');
  const sectionToggle = $('[data-slot="section-toggle"]');
  if (sectionNav && sectionToggle) {
    sectionToggle.addEventListener("click", () => {
      const open = sectionNav.hasAttribute("data-open");
      if (open) {
        sectionNav.removeAttribute("data-open");
      } else {
        sectionNav.setAttribute("data-open", "");
      }
      sectionToggle.setAttribute("aria-expanded", String(!open));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && sectionNav.hasAttribute("data-open")) {
        sectionNav.removeAttribute("data-open");
        sectionToggle.setAttribute("aria-expanded", "false");
        sectionToggle.focus();
      }
    });
  }

  /* ───────────────────────── Contents ───────────────────────── */

  const contentsLinks = $$('[data-component="on-this-page"] a');
  const menu = $('[data-component="contents-menu"]');
  const menuWord = menu?.querySelector('[data-slot="word"]');
  const headingTargets = contentsLinks
    .map((link) => {
      const id = decodeURIComponent(link.getAttribute("href").slice(1));
      const element = document.getElementById(id);
      return element ? { link, element } : null;
    })
    .filter(Boolean);

  let lastLabel = menuWord?.textContent ?? "";

  function updateSpy() {
    if (!headingTargets.length) return;
    const line = 120;
    let current = headingTargets[0];
    for (const entry of headingTargets) {
      if (entry.element.getBoundingClientRect().top <= line) current = entry;
    }
    if (window.scrollY + window.innerHeight >= document.body.scrollHeight - 8) {
      current = headingTargets[headingTargets.length - 1];
    }
    contentsLinks.forEach((link) => link.removeAttribute("aria-current"));
    // "location", as on-this-page.css expects for the current item's pipe and ink.
    current.link.setAttribute("aria-current", "location");

    if (menu?.open && menuWord) {
      const label = current.link.textContent.trim();
      if (label !== lastLabel) {
        menuWord.textContent = label;
        lastLabel = label;
      }
    }
  }

  let spyFrame = 0;
  function onScroll() {
    if (spyFrame) return;
    spyFrame = window.requestAnimationFrame(() => {
      spyFrame = 0;
      updateSpy();
    });
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll, { passive: true });
  updateSpy();

  /* Tabs */

  $$('[data-component="code-tabs"]').forEach((tabs) => {
    const buttons = $$('[role="tab"]', tabs);
    const panels = $$('[role="tabpanel"]', tabs);
    const select = (index) => {
      buttons.forEach((button, i) => {
        const active = i === index;
        button.setAttribute("aria-selected", String(active));
        button.tabIndex = active ? 0 : -1;
        panels[i].hidden = !active;
      });
    };
    buttons.forEach((button, index) => {
      button.addEventListener("click", () => select(index));
      button.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
        event.preventDefault();
        const next = (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
        select(next);
        buttons[next].focus();
      });
    });
  });

  /* ───────────────────────── Section links ───────────────────────── */

  /* A section title copies its own address, and says so beside the title. */
  $$('[data-slot="heading-link"]').forEach((button) => {
    button.addEventListener("click", async () => {
      const slug = (button.dataset.headingLink || "").replace(/^#/, "");
      if (!slug) return;
      const url = `${location.origin}${location.pathname}#${slug}`;
      const ok = await writeClipboard(url);
      if (!ok) return;
      let note = $('[data-slot="heading-copied"]', button.parentElement);
      if (!note) {
        note = document.createElement("span");
        note.dataset.slot = "heading-copied";
        note.setAttribute("aria-live", "polite");
        button.parentElement.append(note);
      }
      note.textContent = strings.linkCopied || "Link copied";
      window.clearTimeout(note._timer);
      note._timer = window.setTimeout(() => {
        note.textContent = "";
      }, 1600);
    });
  });

  /* ───────────────────────── Search ───────────────────────── */

  const dialog = $("[data-search-dialog]");
  const index = window.__UDC_SEARCH__ || [];

  if (dialog) {
    const input = $("input", dialog);
    const results = $('[data-slot="results"]', dialog);
    let rows = [];
    let active = -1;

    const escapeHTML = (value) =>
      value.replace(/[&<>"']/g, (character) => {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
      });

    const mark = (text, query) => {
      const safe = escapeHTML(text);
      if (!query) return safe;
      const escaped = escapeHTML(query).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return safe.replace(new RegExp(`(${escaped})`, "ig"), "<mark>$1</mark>");
    };

    const snippet = (text, query) => {
      if (!query) return text.slice(0, 90);
      const at = text.toLowerCase().indexOf(query.toLowerCase());
      if (at === -1) return text.slice(0, 90);
      return text.slice(Math.max(0, at - 30), Math.max(0, at - 30) + 110);
    };

    function render(query) {
      const term = query.trim().toLowerCase();
      results.innerHTML = "";
      rows = [];
      active = -1;

      if (!term) {
        // Clean: with nothing typed the panel is just the field.
        results.innerHTML = "";
        return;
      }

      const scored = index
        .map((page) => {
          const title = page.title.toLowerCase();
          const headings = (page.headings || "").toLowerCase();
          const text = page.text.toLowerCase();
          let score = 0;
          if (title.includes(term)) score += 40;
          if (headings.includes(term)) score += 12;
          if (text.includes(term)) score += 4;
          if (page.href === "./" || page.href.endsWith("/")) score += 0;
          return { page, score };
        })
        .filter((item) => item.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 9);

      if (!scored.length) {
        results.innerHTML =
          `<p data-slot="empty">${escapeHTML(strings.noResults || "No results for")} ` +
          `“${escapeHTML(query)}”. <a href="../">${escapeHTML(strings.browse || "Browse the docs")}</a></p>`;
        return;
      }

      scored.forEach(({ page }, index_) => {
        const row = document.createElement("a");
        row.href = page.href;
        row.dataset.slot = "option";
        row.setAttribute("role", "option");
        row.innerHTML =
          `<span data-slot="title">${mark(page.title, query)}</span>` +
          `<span data-slot="snippet">${mark(snippet(page.text, query), query)}</span>`;
        row.addEventListener("pointermove", () => setActive(index_));
        results.append(row);
        rows.push(row);
      });
    }

    function setActive(index_) {
      rows.forEach((row, i) => {
        if (i === index_) row.setAttribute("data-active", "");
        else row.removeAttribute("data-active");
      });
      active = index_;
      rows[index_]?.scrollIntoView({ block: "nearest" });
    }

    function open() {
      if (dialog.open) return;
      dialog.showModal();
      input.value = "";
      render("");
      window.requestAnimationFrame(() => input.focus());
    }

    function close() {
      if (!dialog.open) return;
      dialog.close();
      $("[data-search-open]")?.focus();
    }

    $$("[data-search-open]").forEach((button) =>
      button.addEventListener("click", (event) => {
        event.preventDefault();
        open();
      })
    );

    input.addEventListener("input", () => render(input.value));

    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        if (!rows.length) return;
        event.preventDefault();
        const next =
          event.key === "ArrowDown"
            ? (active + 1 + rows.length) % rows.length
            : (active - 1 + rows.length) % rows.length;
        setActive(next);
      } else if (event.key === "Enter") {
        if (rows[active >= 0 ? active : 0]) {
          event.preventDefault();
          rows[active >= 0 ? active : 0].click();
        }
      }
    });

    $('[data-slot="close"]', dialog).addEventListener("click", close);
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) close();
    });
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      close();
    });

    document.addEventListener("keydown", (event) => {
      const typing =
        event.target instanceof HTMLElement &&
        (event.target.tagName === "INPUT" ||
          event.target.tagName === "TEXTAREA" ||
          event.target.isContentEditable);

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        open();
        return;
      }
      if (event.key === "/" && !typing && !dialog.open) {
        event.preventDefault();
        open();
      }
    });
  }

  /* Scroll a hash target into view below the sticky bars without moving on load. */
  if (location.hash) {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (target) {
      window.requestAnimationFrame(() => {
        target.scrollIntoView({ block: "start", behavior: "auto" });
      });
    }
  }

  /* Keep the sidebar's current page visible when the nav list is taller than the
     viewport, so the left rail stays in step with where the reader is. */
  const activeNav = document.querySelector('[data-component="docs-nav"] a[aria-current="page"]');
  if (activeNav) {
    requestAnimationFrame(() => activeNav.scrollIntoView({ block: "nearest", behavior: "auto" }));
  }

  if (reduceMotion.matches) {
    document.documentElement.dataset.reducedMotion = "true";
  }
})();
