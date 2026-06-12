// Auto-size review textareas to their content.
document.querySelectorAll(".value-cell textarea").forEach((area) => {
  const fit = () => {
    area.style.height = "auto";
    area.style.height = Math.max(area.scrollHeight, 56) + "px";
  };
  area.addEventListener("input", fit);
  fit();
});
