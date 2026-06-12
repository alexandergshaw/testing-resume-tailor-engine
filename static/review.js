// Auto-size review textareas to their content.
const fitArea = (area) => {
  area.style.height = "auto";
  area.style.height = Math.max(area.scrollHeight, 56) + "px";
};

document.querySelectorAll(".value-cell textarea").forEach((area) => {
  area.addEventListener("input", () => fitArea(area));
  fitArea(area);
});

// Bank picker: selecting a candidate fills the matching textarea.
document.querySelectorAll(".bank-picker").forEach((picker) => {
  picker.addEventListener("change", () => {
    if (!picker.value) return;
    const area = document.querySelector(
      `textarea[name="${CSS.escape(picker.dataset.target)}"]`);
    if (area) {
      area.value = picker.value;
      fitArea(area);
    }
    picker.selectedIndex = 0;
  });
});
