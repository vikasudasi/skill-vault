fromEventButtons("[data-copy-target]", function (button) {
  const targetId = button.getAttribute("data-copy-target");
  if (!targetId) {
    return;
  }
  const input = document.getElementById(targetId);
  if (!(input instanceof HTMLInputElement)) {
    return;
  }
  navigator.clipboard.writeText(input.value).then(function () {
    button.textContent = "Copied";
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
