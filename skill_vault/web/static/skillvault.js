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
  if (!navigator.clipboard || !navigator.clipboard.writeText) {
    button.textContent = "Clipboard unavailable";
    return;
  }
  navigator.clipboard.writeText(text).then(function () {
    button.textContent = "Copied";
  }).catch(function () {
    button.textContent = "Copy failed";
  });
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
