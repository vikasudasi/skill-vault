// skillvault.js — shared frontend behaviour.
//
// - Clipboard copy with execCommand fallback (kept working).
// - data-confirm dialogs.
// - Tab panels.
// - Alpine dark-mode `theme()` component (consumed by base.html x-data="theme()").
// - highlight.js code highlighting + re-running after HTMX partial swaps.

// --- Alpine dark-mode component --------------------------------------------
window.theme = function () {
  return {
    dark: false,
    init() {
      this.dark = document.documentElement.classList.contains("dark");
    },
    toggle() {
      this.dark = !this.dark;
      this.apply();
    },
    apply() {
      const root = document.documentElement;
      root.classList.toggle("dark", this.dark);
      root.setAttribute("data-theme", this.dark ? "dark" : "light");
      try {
        localStorage.setItem("sv-theme", this.dark ? "dark" : "light");
      } catch (e) {
        /* storage unavailable (private mode) — theme still applies for the tab */
      }
    },
  };
};

// --- highlight.js -----------------------------------------------------------
function runHighlight() {
  if (!window.hljs) {
    return;
  }
  document.querySelectorAll("pre code").forEach(function (el) {
    if (el.dataset.highlighted === "yes") {
      return;
    }
    hljs.highlightElement(el);
    el.dataset.highlighted = "yes";
  });
}

// --- Clipboard copy (kept from the original) --------------------------------
function copyFromButton(button) {
  const targetId = button.getAttribute("data-copy-target");
  if (!targetId) {
    return;
  }
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  const text =
    target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement
      ? target.value
      : target.textContent || "";
  if (!text) {
    return;
  }
  const copied = function () {
    button.textContent = "Copied";
  };
  const failed = function () {
    button.textContent = "Copy failed";
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(copied).catch(failed);
    return;
  }
  // Fallback for non-secure (HTTP) contexts where the Clipboard API is
  // unavailable: select a hidden textarea and execCommand("copy").
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  ta.setSelectionRange(0, text.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (e) {
    ok = false;
  }
  document.body.removeChild(ta);
  if (ok) {
    copied();
  } else {
    failed();
  }
}

fromEventButtons("[data-copy-target]", copyFromButton);

fromEventButtons("[data-confirm]", function (button, event) {
  const message = button.getAttribute("data-confirm") || "Are you sure?";
  if (!window.confirm(message)) {
    event.preventDefault();
  }
});

fromEventButtons("[data-tab-target]", function (button) {
  const target = button.getAttribute("data-tab-target");
  if (!target) {
    return;
  }
  document.querySelectorAll(".tab-panel").forEach(function (panel) {
    panel.classList.remove("is-active");
  });
  document.querySelectorAll(".tab-button").forEach(function (item) {
    item.classList.remove("is-active");
  });
  const panel = document.getElementById(target);
  if (panel) {
    panel.classList.add("is-active");
  }
  button.classList.add("is-active");
  // Re-run highlighting so code blocks in the newly revealed panel (e.g. the
  // raw skill view) get syntax highlighting. runHighlight() skips nodes it has
  // already processed via the data-highlighted guard, so this is idempotent.
  runHighlight();
});

function fromEventButtons(selector, handler) {
  document.querySelectorAll(selector).forEach(function (button) {
    button.addEventListener("click", function (event) {
      handler(button, event);
    });
  });
}

// --- Initialisation ----------------------------------------------------------
document.addEventListener("DOMContentLoaded", function () {
  runHighlight();
});

// After an HTMX partial swap, re-bind behaviours on the newly injected nodes
// so copy buttons, tabs, and code blocks keep working in the fragment.
document.addEventListener("htmx:afterSwap", function () {
  runHighlight();
  fromEventButtons("[data-copy-target]", copyFromButton);
});
