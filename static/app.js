// Tailor page: a pure client of /api/v1 — the same calls external apps make.
let templateFile = null;
let lastProposals = null;
// The workflow that produced the current review; /tailor reuses it so the
// downloaded doc matches the slots on screen even if the toggle changes after.
let activeWorkflow = "legacy";
const READONLY = document.body.dataset.readonly === "1";

const selectedWorkflow = () =>
  document.querySelector('input[name="workflow"]:checked').value;

const summarizeRequest = (extraFields = {}) => {
  const lines = [
    `workflow: ${activeWorkflow}`,
    `posting: ${$("#posting").value.length} chars`,
    `template: ${templateFile ? `${templateFile.name} (${templateFile.size} bytes)` : "bundled default"}`,
  ];
  for (const [name, value] of Object.entries(extraFields)) {
    lines.push(`${name}: ${value}`);
  }
  if (apiKey()) lines.push("X-API-Key: ***");
  return lines.join("\n");
};

const buildFormData = () => {
  const fd = new FormData();
  fd.append("posting", $("#posting").value);
  fd.append("workflow", activeWorkflow);
  const company = $("#target-company").value.trim();
  if (company) fd.append("target_organization", company);
  if (templateFile) fd.append("template", templateFile);  // omit -> bundled default
  return fd;
};

$("#proposals-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  templateFile = $("#template").files[0] || null;
  activeWorkflow = selectedWorkflow();
  $("#proposals-btn").disabled = true;
  try {
    const res = await fetch("/api/v1/proposals", {
      method: "POST", body: buildFormData(), headers: apiHeaders(),
    });
    const data = await res.json();
    logExchange("POST", "/api/v1/proposals", summarizeRequest(), res.status, data);
    if (!res.ok) { flash(`${data.error}: ${data.detail}`, true); return; }
    lastProposals = data;
    renderReview(data);
  } catch (err) {
    flash(`Request failed: ${err}`, true);
  } finally {
    $("#proposals-btn").disabled = false;
  }
});

function renderReview(data) {
  const rows = data.slots.map((slot) => {
    const badge = `<span class="badge badge-${slot.strategy}">${slot.strategy}</span>`;
    const single = slot.single_brace
      ? ' <span class="badge badge-warn" title="Matched a single-brace token; blank it if literal">single&nbsp;brace</span>'
      : "";
    const context = escapeHtml(slot.context)
      .replace(escapeHtml(slot.raw), `<mark>${escapeHtml(slot.raw)}</mark>`);
    const note = slot.note ? `<div class="note">${escapeHtml(slot.note)}</div>` : "";
    const options = slot.candidates.map((c) =>
      `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
    const picker = slot.candidates.length
      ? `<select class="bank-picker" data-target="${escapeHtml(slot.key)}">
           <option value="">— insert from bank (${slot.candidates.length}) —</option>${options}
         </select>` : "";
    const remember = READONLY ? "" :
      `<label class="remember" title="Save this value to the bank for ${escapeHtml(slot.name)}">
         <input type="checkbox" data-remember="${escapeHtml(slot.key)}"> remember
       </label>`;
    return `<tr class="${slot.value ? "" : "manual-row"}">
      <td class="meta">${badge}${single}
        <div class="ph-name">${escapeHtml(slot.raw)}</div>
        <div class="context">…${context}…</div>${note}
      </td>
      <td class="value-cell">
        <textarea rows="2" data-key="${escapeHtml(slot.key)}">${escapeHtml(slot.value)}</textarea>
        <div class="value-tools">${picker}${remember}</div>
      </td>
    </tr>`;
  }).join("");
  $("#review-rows").innerHTML = rows;

  const manual = data.slots.filter((s) => !s.value).length;
  const wfLabel = data.workflow === "composed" ? "New APIs (composed)" : "Legacy engine";
  $("#review-summary").innerHTML =
    `<span class="wf-pill wf-${escapeHtml(data.workflow || "legacy")}">${wfLabel}</span> ` +
    `${data.slots.length} placeholders found` +
    (manual ? `, ${manual} need your input` : "") +
    ". Blank fields keep their placeholder in the document.";
  if (data.meta && data.meta.degraded) {
    flash(`New APIs unavailable — fell back to the legacy engine` +
          (data.meta.reason ? ` (${data.meta.reason})` : "."), true);
  }

  $("#keyword-groups").innerHTML = Object.entries(data.keywords).map(
    ([category, kws]) => `<h3>${escapeHtml(category.replace(/_/g, " "))}</h3>
      <ul class="keywords">${kws.map((kw) =>
        `<li><span class="kw">${escapeHtml(kw.canonical)}</span>` +
        `<span class="score" title="score ${kw.score}">${kw.count}×</span></li>`).join("")}
      </ul>`).join("");

  renderResearch(data.research || []);
  renderNews(data.company_news || {});

  document.querySelectorAll(".bank-picker").forEach((picker) => {
    picker.addEventListener("change", () => {
      if (!picker.value) return;
      const area = document.querySelector(
        `textarea[data-key="${CSS.escape(picker.dataset.target)}"]`);
      if (area) area.value = picker.value;
      picker.selectedIndex = 0;
    });
  });

  $("#review").hidden = false;
  $("#review").scrollIntoView({ behavior: "smooth" });
}

// Favorable company news (composed workflow, target company given). Volatile +
// advisory — shown with date/source/tone for the human to rephrase, never auto-inserted.
function renderNews(news) {
  const panel = $("#news-panel");
  if (!panel) return;
  const articles = news.articles || [];
  if (!articles.length) { panel.hidden = true; panel.innerHTML = ""; return; }
  panel.hidden = false;
  const asOf = news.as_of ? ` as of ${escapeHtml(news.as_of)}` : "";
  panel.innerHTML = `<h2>Company news</h2>` +
    `<p class="hint">Favorable recent items${asOf} — verify the date and rephrase the
     fact in your own words; don't paste article text.</p>` +
    articles.map((a) => {
      const date = a.published ? escapeHtml(String(a.published).slice(0, 10)) : "";
      const tone = a.tone != null ? `tone ${escapeHtml(String(a.tone))}` : "";
      const title = a.url
        ? `<a href="${escapeHtml(a.url)}" target="_blank" rel="noopener">${escapeHtml(a.title || a.url)}</a>`
        : escapeHtml(a.title || "");
      return `<div class="research-item">
        <div class="research-summary">${title}</div>
        <div class="research-source">${escapeHtml(a.source || "")} · ${date} · ${tone}</div>
      </div>`;
    }).join("") +
    (news.attributions || []).map((s) =>
      `<div class="research-source">${escapeHtml(s)}</div>`).join("");
}

// Advisory research context (composed workflow only) — never auto-inserted.
function renderResearch(research) {
  const panel = $("#research-panel");
  if (!panel) return;
  if (!research.length) { panel.hidden = true; panel.innerHTML = ""; return; }
  panel.hidden = false;
  panel.innerHTML = "<h2>Research context</h2>" +
    `<p class="hint">Advisory only — from the Researcher API. Copy in what's useful;
     nothing here is auto-inserted.</p>` +
    research.map((item) => {
      const sources = (item.sources || [])
        .map((s) => escapeHtml(s.attribution || s.name || s.url || "")).join("; ");
      return `<div class="research-item">
        <div class="research-emphasis">${escapeHtml(item.emphasis || "")}</div>
        <div class="research-summary">${escapeHtml(item.summary || "")}</div>
        ${sources ? `<div class="research-source">${sources}</div>` : ""}
      </div>`;
    }).join("");
}

$("#tailor-btn").addEventListener("click", async () => {
  const values = {};
  document.querySelectorAll("#review textarea[data-key]").forEach((area) => {
    values[area.dataset.key] = area.value;
  });
  const remember = [...document.querySelectorAll("input[data-remember]:checked")]
    .map((box) => box.dataset.remember);

  const fd = buildFormData();
  fd.append("values", JSON.stringify(values));
  if (remember.length) fd.append("remember", JSON.stringify(remember));

  $("#tailor-btn").disabled = true;
  try {
    // Accept: application/json so the report is visible in the log panel;
    // the docx arrives base64-encoded and is downloaded client-side.
    const res = await fetch("/api/v1/tailor", {
      method: "POST", body: fd,
      headers: apiHeaders({ Accept: "application/json" }),
    });
    const data = await res.json();
    const loggable = { ...data };
    if (loggable.docx_b64) loggable.docx_b64 = `<${loggable.docx_b64.length} base64 chars>`;
    logExchange("POST", "/api/v1/tailor",
      summarizeRequest({ values: `${Object.keys(values).length} keys`,
                         remember: remember.length }),
      res.status, loggable);
    if (!res.ok) { flash(`${data.error}: ${data.detail}`, true); return; }

    const bytes = Uint8Array.from(atob(data.docx_b64), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "Tailored Resume.docx";
    link.click();
    URL.revokeObjectURL(link.href);

    const saved = data.report.remembered ? data.report.remembered.length : 0;
    const renderer = data.report.meta && data.report.meta.renderer;
    const via = renderer === "generator" ? " (rendered via Document Generator)" : "";
    flash(`Downloaded${via}. ${data.report.unfilled.length} slot(s) left unfilled` +
          (saved ? `; ${saved} value(s) saved to bank.` : "."));
  } catch (err) {
    flash(`Request failed: ${err}`, true);
  } finally {
    $("#tailor-btn").disabled = false;
  }
});

$("#start-over").addEventListener("click", (event) => {
  event.preventDefault();
  $("#review").hidden = true;
  lastProposals = null;
  window.scrollTo({ top: 0, behavior: "smooth" });
});

$("#copy-curl").addEventListener("click", async () => {
  const key = apiKey() ? ` -H "X-API-Key: ${apiKey()}"` : "";
  const curl = `curl -X POST ${location.origin}/api/v1/proposals${key} \\
  -F "posting=<paste posting text>" \\
  -F "template=@Template Resume.docx"`;
  await navigator.clipboard.writeText(curl);
  flash("curl command copied to clipboard.");
});
