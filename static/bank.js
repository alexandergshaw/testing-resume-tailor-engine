// Bank page: thin client over /api/v1/bank.
const READONLY = document.body.dataset.readonly === "1";

const apiCall = async (method, url, body) => {
  const options = { method, headers: apiHeaders(body ? { "Content-Type": "application/json" } : {}) };
  if (body) options.body = JSON.stringify(body);
  const res = await fetch(url, options);
  const data = await res.json();
  logExchange(method, url, body ? JSON.stringify(body) : "(no body)", res.status, data);
  if (!res.ok) flash(`${data.error}: ${data.detail}`, true);
  return { ok: res.ok, data };
};

async function refresh() {
  const { ok, data } = await apiCall("GET", "/api/v1/bank");
  if (!ok) return;

  $("#entries-heading").textContent = `Entries (${data.entries.length})`;
  $("#entries").innerHTML = data.entries.map((entry) => `
    <div class="bank-entry" data-id="${escapeHtml(entry.id)}">
      <textarea rows="1" data-field="text" ${READONLY ? "disabled" : ""}>${escapeHtml(entry.text)}</textarea>
      <input data-field="slots" value="${escapeHtml(entry.slots.join(", "))}" title="Slots" ${READONLY ? "disabled" : ""}>
      <input data-field="tags" value="${escapeHtml(entry.tags.join(", "))}" title="Tags" ${READONLY ? "disabled" : ""}>
      <span class="bank-actions">
        ${READONLY ? "" : `<button type="button" class="small" data-action="save">Save</button>
        <button type="button" class="small danger" data-action="delete">Delete</button>`}
      </span>
      <span class="entry-id">${escapeHtml(entry.id)}</span>
    </div>`).join("") || "<p class='hint'>No entries yet.</p>";

  const slots = [...new Set(data.entries.flatMap((e) => e.slots))].sort();
  const datalist = $("#slot-names");
  if (datalist) {
    datalist.innerHTML = slots.map((s) => `<option value="${escapeHtml(s)}">`).join("");
  }

  $("#profile-form").innerHTML = Object.entries(data.profile).map(
    ([key, value]) => `<label>${escapeHtml(key)}
      <input data-profile-key="${escapeHtml(key)}" value="${escapeHtml(value)}" ${READONLY ? "disabled" : ""}>
    </label>`).join("") +
    (READONLY ? "" : `<button type="submit">Save profile</button>`);
}

const csv = (raw) => raw.split(",").map((part) => part.trim()).filter(Boolean);

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const row = button.closest(".bank-entry");
  const id = row.dataset.id;
  if (button.dataset.action === "delete") {
    const { ok } = await apiCall("DELETE", `/api/v1/bank/entries/${encodeURIComponent(id)}`);
    if (ok) refresh();
  } else {
    const { ok } = await apiCall("PUT", `/api/v1/bank/entries/${encodeURIComponent(id)}`, {
      text: row.querySelector('[data-field="text"]').value,
      slots: csv(row.querySelector('[data-field="slots"]').value),
      tags: csv(row.querySelector('[data-field="tags"]').value),
    });
    if (ok) { flash(`Updated '${id}'.`); refresh(); }
  }
});

const addForm = $("#add-form");
if (addForm) {
  addForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const { ok } = await apiCall("POST", "/api/v1/bank/entries", {
      text: $("#add-text").value,
      slot: $("#add-slot").value,
      tags: csv($("#add-tags").value),
    });
    if (ok) {
      addForm.reset();
      flash("Added to bank.");
      refresh();
    }
  });
}

$("#profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = {};
  document.querySelectorAll("[data-profile-key]").forEach((input) => {
    values[input.dataset.profileKey] = input.value;
  });
  const { ok } = await apiCall("POST", "/api/v1/bank/profile", { values });
  if (ok) flash("Profile saved.");
});

refresh();
