// Shared helpers for the API-client pages.
const $ = (selector) => document.querySelector(selector);

const apiKey = () => localStorage.getItem("apiKey") || "";

const apiHeaders = (extra = {}) => {
  const headers = { ...extra };
  if (apiKey()) headers["X-API-Key"] = apiKey();
  return headers;
};

const escapeHtml = (text) =>
  String(text).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

const flash = (message, isError = false) => {
  const box = $("#flash");
  box.textContent = message;
  box.hidden = false;
  box.classList.toggle("flash-error", isError);
  setTimeout(() => { box.hidden = true; }, 6000);
};

// Request/response panel: shows the live API traffic this page generates.
const logExchange = (method, url, requestSummary, status, responseBody) => {
  const panel = $("#api-log");
  if (!panel) return;
  const stamp = new Date().toLocaleTimeString();
  const body = typeof responseBody === "string"
    ? responseBody : JSON.stringify(responseBody, null, 2);
  panel.textContent =
    `[${stamp}] ${method} ${url}\n--- request ---\n${requestSummary}\n` +
    `--- response (${status}) ---\n${body}\n\n` + panel.textContent;
  const details = panel.closest("details");
  if (details) details.open = true;
};

// API key field wiring (present on both pages).
document.addEventListener("DOMContentLoaded", () => {
  const field = $("#api-key");
  if (!field) return;
  field.value = apiKey();
  field.addEventListener("change", () => {
    localStorage.setItem("apiKey", field.value.trim());
    flash("API key saved locally.");
  });
});
