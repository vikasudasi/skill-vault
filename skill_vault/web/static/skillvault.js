fromEventButtons("[data-copy-target]", function (button) {
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
});

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
});

function fromEventButtons(selector, handler) {
  document.querySelectorAll(selector).forEach(function (button) {
    button.addEventListener("click", function (event) {
      handler(button, event);
    });
  });
}
