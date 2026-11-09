(() => {
  // Item forms: show only the chosen category's block of extra fields.
  // The server reads only that block too, so values typed into another block are never saved.
  const section = document.querySelector("[data-custom-fields]");
  const select = document.querySelector('select[name="category"]');
  if (!section || !select) return;
  const hint = section.querySelector("[data-custom-fields-hint]");

  function showChosen() {
    let shown = null;
    section.querySelectorAll(".custom-field-block").forEach((block) => {
      const visible = block.dataset.category === select.value;
      block.hidden = !visible;
      if (visible) shown = block;
    });
    if (hint) hint.hidden = Boolean(select.value);
    // Maps can only measure themselves once visible: tell location-picker.js.
    if (shown) shown.dispatchEvent(new CustomEvent("customfields:shown", { bubbles: true }));
  }

  select.addEventListener("change", showChosen);
  showChosen();
})();
