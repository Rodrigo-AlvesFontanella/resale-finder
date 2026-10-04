const searchForm = document.getElementById("search-form");
const searchStatus = document.getElementById("search-status");
const manualForm = document.getElementById("manual-form");
const manualStatus = document.getElementById("manual-status");
const resultsBody = document.getElementById("results-body");
const termFilter = document.getElementById("term-filter");
const strategySummary = document.getElementById("strategy-summary");

function badgeClass(score) {
  if (score === null || score === undefined) return "bad";
  if (score >= 55) return "good";
  if (score >= 35) return "mid";
  return "bad";
}

function formatPrice(value) {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function renderStrategy(items) {
  strategySummary.innerHTML = "";
  const top = items
    .filter((i) => i.priority_score !== null && i.priority_score !== undefined)
    .slice(0, 5);

  if (top.length === 0) {
    strategySummary.innerHTML = '<p class="strategy-empty">Faça uma busca para ver a estratégia de priorização.</p>';
    return;
  }

  top.forEach((item, idx) => {
    const div = document.createElement("div");
    div.className = "strategy-item";
    const title = item.url && item.url.startsWith("http")
      ? `<a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>`
      : item.title;
    div.innerHTML = `
      <span class="rank">#${idx + 1}</span>
      <span class="badge ${badgeClass(item.priority_score)}">${item.priority_score}</span>
      ${title} — ${formatPrice(item.price)}
      <div class="why">${item.priority_reasons || "sem sinais fortes de prioridade"}</div>
    `;
    strategySummary.appendChild(div);
  });
}

function renderItems(items) {
  resultsBody.innerHTML = "";
  for (const item of items) {
    const tr = document.createElement("tr");

    const scoreTd = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge ${badgeClass(item.priority_score)}`;
    badge.textContent = item.priority_score !== null ? `${item.priority_score}` : "-";
    scoreTd.appendChild(badge);
    tr.appendChild(scoreTd);

    const titleTd = document.createElement("td");
    if (item.url && item.url.startsWith("http")) {
      const a = document.createElement("a");
      a.href = item.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = item.title;
      titleTd.appendChild(a);
    } else {
      titleTd.textContent = item.title;
    }
    if (item.label) {
      const small = document.createElement("div");
      small.className = "flags";
      small.textContent = item.label;
      titleTd.appendChild(small);
    }
    tr.appendChild(titleTd);

    const priceTd = document.createElement("td");
    priceTd.textContent = formatPrice(item.price);
    tr.appendChild(priceTd);

    const sourceTd = document.createElement("td");
    sourceTd.textContent = item.source;
    tr.appendChild(sourceTd);

    const locTd = document.createElement("td");
    locTd.textContent = item.location || "-";
    tr.appendChild(locTd);

    const flagsTd = document.createElement("td");
    flagsTd.className = "flags";
    flagsTd.textContent = item.priority_reasons || item.flags || "-";
    tr.appendChild(flagsTd);

    const actionsTd = document.createElement("td");
    const delBtn = document.createElement("button");
    delBtn.className = "delete-btn";
    delBtn.textContent = "✕";
    delBtn.title = "Remover";
    delBtn.onclick = async () => {
      await fetch(`/api/listings/${item.id}`, { method: "DELETE" });
      loadListings(selectedTerm);
    };
    actionsTd.appendChild(delBtn);
    tr.appendChild(actionsTd);

    resultsBody.appendChild(tr);
  }
}

let selectedTerm = "";

async function loadTerms() {
  const res = await fetch("/api/search-terms");
  const data = await res.json();
  termFilter.innerHTML = '<option value="">Todos os termos</option>';
  for (const t of data.terms) {
    const opt = document.createElement("option");
    opt.value = t.term;
    opt.textContent = `${t.term} (${t.count})`;
    termFilter.appendChild(opt);
  }
  termFilter.value = selectedTerm;
}

const toggleAllBtn = document.getElementById("toggle-all");
const resultsCount = document.getElementById("results-count");
let showAll = false;

async function loadListings(searchTerm) {
  const params = new URLSearchParams();
  if (searchTerm) params.set("search_term", searchTerm);
  params.set("limit", showAll ? "0" : "50");
  const res = await fetch(`/api/listings?${params}`);
  const data = await res.json();
  renderItems(data.items);
  renderStrategy(data.items);
  resultsCount.textContent = data.total > data.count
    ? `Mostrando ${data.count} de ${data.total} anúncios (os de maior prioridade).`
    : `${data.total} anúncios.`;
  toggleAllBtn.textContent = showAll ? "Mostrar só os 50 melhores" : "Mostrar todos";
}

toggleAllBtn.addEventListener("click", () => {
  showAll = !showAll;
  loadListings(selectedTerm);
});

async function applyConfig() {
  try {
    const res = await fetch("/api/config");
    const cfg = await res.json();
    if (!cfg.live_search) {
      document.getElementById("search-section").hidden = true;
    }
  } catch (_) {
    // sem config, mantem o formulario visivel
  }
}

searchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = document.getElementById("query").value.trim();
  const maxPages = parseInt(document.getElementById("max-pages").value, 10);
  const onlyPoa = document.getElementById("only-poa").checked;
  searchStatus.textContent = "Buscando na OLX...";
  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, max_pages: maxPages, only_poa_metro: onlyPoa }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Erro na busca");
    }
    const data = await res.json();
    searchStatus.textContent = `${data.count} anúncios encontrados/atualizados para "${query}"${onlyPoa ? " na Grande Porto Alegre" : ""}.`;
    await loadTerms();
    selectedTerm = query;
    await loadListings(query);
  } catch (err) {
    searchStatus.textContent = `Erro: ${err.message}`;
  }
});

manualForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    title: document.getElementById("m-title").value.trim(),
    price: parseFloat(document.getElementById("m-price").value),
    search_term: document.getElementById("m-search-term").value.trim(),
    url: document.getElementById("m-url").value.trim() || null,
    location: document.getElementById("m-location").value.trim() || null,
    description: document.getElementById("m-description").value.trim() || null,
  };
  manualStatus.textContent = "Avaliando...";
  try {
    const res = await fetch("/api/manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Erro ao salvar item");
    }
    const item = await res.json();
    manualStatus.textContent = `Item avaliado: ${item.label} (prioridade ${item.priority_score})`;
    manualForm.reset();
    await loadTerms();
    selectedTerm = payload.search_term;
    await loadListings(payload.search_term);
  } catch (err) {
    manualStatus.textContent = `Erro: ${err.message}`;
  }
});

termFilter.addEventListener("change", () => {
  selectedTerm = termFilter.value;
  loadListings(selectedTerm);
});

applyConfig();
loadTerms();
loadListings("");
