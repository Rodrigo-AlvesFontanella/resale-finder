const state = {
  section: "revenda",
  selectedTerm: "",
  showAll: false,
  showHidden: false,
  liveSearch: false,
  lastPending: false,
};

const $ = (id) => document.getElementById(id);

const els = {
  tabs: document.querySelectorAll(".tab"),
  syncBtn: $("sync-btn"),
  syncStatus: $("sync-status"),
  strategyTitle: $("strategy-title"),
  strategyHint: $("strategy-hint"),
  strategy: $("strategy-summary"),
  termFilter: $("term-filter"),
  showHidden: $("show-hidden"),
  toggleAll: $("toggle-all"),
  count: $("results-count"),
  body: $("results-body"),
  pharmacyTools: $("pharmacy-tools"),
  pharmacyLinks: $("pharmacy-links"),
  searchSection: $("search-section"),
  searchForm: $("search-form"),
  searchStatus: $("search-status"),
  query: $("query"),
  maxPages: $("max-pages"),
  onlyPoa: $("only-poa"),
  pasteText: $("paste-text"),
  parseBtn: $("parse-btn"),
  parseStatus: $("parse-status"),
  quickTerm: $("quick-term"),
  manualForm: $("manual-form"),
  manualStatus: $("manual-status"),
  mSection: $("m-section"),
  mTitle: $("m-title"),
  mPrice: $("m-price"),
  mOldPrice: $("m-old-price"),
  mExpires: $("m-expires"),
  mTerm: $("m-search-term"),
  mUrl: $("m-url"),
  mLocation: $("m-location"),
  mDescription: $("m-description"),
};

const STORE_URLS = {
  panvel: "https://www.panvel.com/panvel/buscarProduto.do?termo=",
  paguemenos: "https://www.paguemenos.com.br/busca?q=",
  pacheco: "https://www.drogariapacheco.com.br/busca?q=",
  raia: "https://www.drogaraia.com.br/busca?q=",
};

async function api(url, options = {}) {
  const res = await fetch(url, options);
  let data = null;
  try { data = await res.json(); } catch (_) { /* resposta sem JSON */ }
  if (!res.ok) {
    const err = new Error((data && data.detail) || `Erro ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function postJSON(url, body) {
  return api(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "dataset") Object.assign(node.dataset, v);
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child) node.appendChild(child);
  }
  return node;
}

function safeHref(url) {
  return url && /^https?:\/\//.test(url) ? url : null;
}

function formatPrice(value) {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function badgeClass(score) {
  if (score === null || score === undefined) return "bad";
  if (score >= 55) return "good";
  if (score >= 35) return "mid";
  return "bad";
}

function timeAgo(iso) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "agora há pouco";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `há ${hours} h`;
  return `há ${Math.round(hours / 24)} dias`;
}

/* ---------- Sync ---------- */

function renderSyncStatus(s) {
  if (s.pending) {
    els.syncStatus.textContent = "Pedido enviado. Aguardando o sync rodar no seu PC (leva uns 5 minutos).";
  } else if (s.last_sync_at) {
    els.syncStatus.textContent = `Última sincronização: ${timeAgo(s.last_sync_at)}.`;
  } else {
    els.syncStatus.textContent = "Nenhuma sincronização ainda.";
  }
  els.syncBtn.disabled = s.pending;
}

async function loadSyncStatus() {
  try {
    const s = await api("/api/sync-status");
    renderSyncStatus(s);
    if (state.lastPending && !s.pending) {
      await refreshAll();
    }
    state.lastPending = s.pending;
  } catch (_) {
    els.syncStatus.textContent = "Não consegui falar com o servidor agora.";
  }
}

els.syncBtn.addEventListener("click", async () => {
  els.syncBtn.disabled = true;
  try {
    const data = await postJSON("/api/sync-request", {});
    state.lastPending = data.pending;
    renderSyncStatus(data);
  } catch (err) {
    els.syncStatus.textContent = err.message;
    els.syncBtn.disabled = false;
  }
});

/* ---------- Secao e filtros ---------- */

function applySectionUI() {
  const isPharmacy = state.section === "farmacia";
  els.tabs.forEach((t) => {
    const active = t.dataset.section === state.section;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", String(active));
  });
  els.pharmacyTools.hidden = !isPharmacy;
  els.pharmacyLinks.hidden = !isPharmacy;
  els.searchSection.hidden = isPharmacy || !state.liveSearch;
  els.strategyTitle.textContent = isPharmacy ? "Melhores promoções de farmácia" : "Melhores oportunidades de revenda";
  els.strategyHint.textContent = isPharmacy
    ? "Ordenado pela combinação de desconto, recência e validade. Confira a validade antes de comprar."
    : "Ordenado pela combinação de preço abaixo da mediana, categoria de giro rápido e anúncio recente.";
  els.mSection.value = state.section;
}

els.tabs.forEach((t) => {
  t.addEventListener("click", async () => {
    if (state.section === t.dataset.section) return;
    state.section = t.dataset.section;
    state.selectedTerm = "";
    applySectionUI();
    await refreshAll();
  });
});

async function loadTerms() {
  const data = await api(`/api/search-terms?section=${state.section}`);
  els.termFilter.innerHTML = "";
  els.termFilter.appendChild(el("option", { value: "", text: "Todos os termos" }));
  for (const t of data.terms) {
    els.termFilter.appendChild(el("option", { value: t.term, text: `${t.term} (${t.count})` }));
  }
  const exists = data.terms.some((t) => t.term === state.selectedTerm);
  if (!exists) state.selectedTerm = "";
  els.termFilter.value = state.selectedTerm;
}

async function loadListings() {
  const params = new URLSearchParams({
    section: state.section,
    limit: state.showAll ? "0" : "50",
    include_hidden: String(state.showHidden),
  });
  if (state.selectedTerm) params.set("search_term", state.selectedTerm);
  const data = await api(`/api/listings?${params}`);
  renderStrategy(data.items.filter((i) => !i.hidden));
  renderTable(data.items);
  els.count.textContent = data.total > data.count
    ? `Mostrando ${data.count} de ${data.total} itens (os de maior prioridade).`
    : `${data.total} itens.`;
  els.toggleAll.textContent = state.showAll ? "Mostrar só os 50 melhores" : "Mostrar todos";
}

async function refreshAll() {
  try {
    await loadTerms();
    await loadListings();
  } catch (err) {
    els.count.textContent = `Erro ao carregar: ${err.message}`;
  }
}

els.termFilter.addEventListener("change", () => {
  state.selectedTerm = els.termFilter.value;
  loadListings();
});

els.showHidden.addEventListener("change", () => {
  state.showHidden = els.showHidden.checked;
  loadListings();
});

els.toggleAll.addEventListener("click", () => {
  state.showAll = !state.showAll;
  loadListings();
});

/* ---------- Estrategia (top 5) ---------- */

function renderStrategy(items) {
  els.strategy.replaceChildren();
  const top = items
    .filter((i) => i.priority_score !== null && i.priority_score !== undefined)
    .filter((i) => !(i.expiry && i.expiry.level === "vencido"))
    .slice(0, 5);

  if (top.length === 0) {
    els.strategy.appendChild(el("p", {
      class: "strategy-empty",
      text: state.section === "farmacia"
        ? "Nenhuma promoção ainda. Cole uma promoção ou sincronize pra começar."
        : "Nenhum anúncio ainda. Sincronize os dados pra ver as melhores oportunidades.",
    }));
    return;
  }

  top.forEach((item, idx) => {
    const url = safeHref(item.url);
    const titleNode = url
      ? el("a", { href: url, target: "_blank", rel: "noopener", text: item.title })
      : el("span", { text: item.title });
    const expiry = item.expiry
      ? el("span", { class: `badge ${item.expiry.level === "vencido" ? "expired" : item.expiry.level === "atencao" ? "warn" : "ok"}`, text: item.expiry.text })
      : null;

    els.strategy.appendChild(el("div", { class: "strategy-item" }, [
      el("div", { class: "top" }, [
        el("span", { class: "rank", text: `#${idx + 1}` }),
        el("span", { class: `badge ${badgeClass(item.priority_score)}`, text: String(item.priority_score) }),
        titleNode,
        el("span", { text: `— ${formatPrice(item.price)}` }),
        expiry,
      ]),
      el("div", { class: "why", text: item.priority_reasons || "sem sinais fortes de prioridade" }),
    ]));
  });
}

/* ---------- Tabela ---------- */

function buildHistoryRow(listing) {
  const cell = el("td", { colspan: "7" });
  const box = el("div", { class: "history", text: "Carregando histórico..." });
  cell.appendChild(box);
  api(`/api/listings/${listing.id}/history`)
    .then((data) => {
      if (data.items.length === 0) {
        box.textContent = "Sem histórico de preço ainda.";
        return;
      }
      const parts = data.items.map((h) => {
        const when = h.seen_at ? new Date(h.seen_at).toLocaleDateString("pt-BR") : "";
        return `${formatPrice(h.price)} (${when})`;
      });
      box.textContent = `Histórico: ${parts.join("  →  ")}`;
    })
    .catch((err) => { box.textContent = `Erro: ${err.message}`; });
  return el("tr", { class: "history-row" }, [cell]);
}

function buildPriceCell(item) {
  const children = [el("strong", { text: formatPrice(item.price) })];
  if (item.old_price && item.old_price > item.price + 0.01) {
    children.push(el("span", { class: "old-price", text: formatPrice(item.old_price) }));
  }
  if (item.dropped) {
    children.push(el("span", { class: "badge drop", text: `↓ caiu de ${formatPrice(item.prev_price)}` }));
  }
  if (item.min_price !== null && item.min_price < item.price - 0.01) {
    children.push(el("div", { class: "muted", text: `menor já visto: ${formatPrice(item.min_price)}` }));
  }
  return el("td", { "data-label": "Preço" }, children);
}

function buildExpiryCell(item) {
  if (!item.expiry) return el("td", { "data-label": "Validade", text: "-" });
  const cls = item.expiry.level === "vencido" ? "expired" : item.expiry.level === "atencao" ? "warn" : "ok";
  return el("td", { "data-label": "Validade" }, [el("span", { class: `badge ${cls}`, text: item.expiry.text })]);
}

function buildActions(item, rerow) {
  const hideBtn = el("button", {
    type: "button",
    class: "icon-btn",
    title: item.hidden ? "Mostrar de novo" : "Ocultar (já comprei ou não quero)",
    text: item.hidden ? "Mostrar" : "Ocultar",
  });
  hideBtn.addEventListener("click", async () => {
    try {
      await api(`/api/listings/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hidden: !item.hidden }),
      });
      await loadListings();
    } catch (err) {
      els.count.textContent = `Erro: ${err.message}`;
    }
  });

  const histBtn = el("button", { type: "button", class: "icon-btn", title: "Ver histórico de preço", text: "Histórico" });
  histBtn.addEventListener("click", () => rerow());

  const delBtn = el("button", { type: "button", class: "icon-btn danger", title: "Remover", text: "✕" });
  delBtn.addEventListener("click", async () => {
    if (!confirm("Remover este item?")) return;
    try {
      await api(`/api/listings/${item.id}`, { method: "DELETE" });
      await refreshAll();
    } catch (err) {
      els.count.textContent = `Erro: ${err.message}`;
    }
  });

  return el("td", { class: "actions", "data-label": "Ações" }, [histBtn, hideBtn, delBtn]);
}

function renderTable(items) {
  els.body.replaceChildren();
  for (const item of items) {
    const url = safeHref(item.url);
    const titleNode = url
      ? el("a", { href: url, target: "_blank", rel: "noopener", text: item.title })
      : el("span", { text: item.title });

    const rowClass = item.hidden ? "hidden-row" : "";
    const tr = el("tr", { class: rowClass });

    const scoreCell = el("td", { "data-label": "Prioridade" }, [
      el("span", { class: `badge ${badgeClass(item.priority_score)}`, text: item.priority_score !== null ? String(item.priority_score) : "-" }),
    ]);

    const itemCell = el("td", { "data-label": "Item" }, [
      titleNode,
      item.label ? el("div", { class: "muted", text: item.label }) : null,
    ]);

    const whereText = [item.source, item.location].filter(Boolean).join(" · ");
    const whyText = item.priority_reasons || item.flags || "";
    const whyCell = el("td", { "data-label": "Por quê" }, [
      el("div", { class: "reasons", text: whyText }),
    ]);

    let histRow = null;
    let histOpen = false;
    const rerow = () => {
      if (histOpen) {
        histRow.remove();
        histOpen = false;
        return;
      }
      histRow = buildHistoryRow(item);
      tr.after(histRow);
      histOpen = true;
    };

    tr.append(
      scoreCell,
      itemCell,
      buildPriceCell(item),
      buildExpiryCell(item),
      el("td", { "data-label": "Onde", text: whereText || "-" }),
      whyCell,
      buildActions(item, rerow),
    );
    els.body.appendChild(tr);
  }
}

/* ---------- Farmacia: colar promocao e links ---------- */

els.parseBtn.addEventListener("click", async () => {
  const text = els.pasteText.value.trim();
  if (!text) {
    els.parseStatus.textContent = "Cole o texto da promoção primeiro.";
    return;
  }
  try {
    const data = await postJSON("/api/parse-promo", { text });
    els.mSection.value = "farmacia";
    if (data.title) els.mTitle.value = data.title;
    if (data.price !== null) els.mPrice.value = data.price;
    els.mOldPrice.value = data.old_price ?? "";
    els.mExpires.value = data.expires_at || "";
    els.mDescription.value = text;
    els.parseStatus.textContent = data.warnings.length
      ? data.warnings.join(" ")
      : "Achei os dados. Confira e salve.";
    els.manualForm.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    els.parseStatus.textContent = `Erro: ${err.message}`;
  }
});

function updateQuickLinks() {
  const term = encodeURIComponent(els.quickTerm.value.trim());
  document.querySelectorAll(".chip[data-store]").forEach((a) => {
    a.href = STORE_URLS[a.dataset.store] + term;
  });
}
els.quickTerm.addEventListener("input", updateQuickLinks);

/* ---------- Formularios ---------- */

els.manualForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    section: els.mSection.value,
    title: els.mTitle.value.trim(),
    price: parseFloat(els.mPrice.value),
    old_price: els.mOldPrice.value ? parseFloat(els.mOldPrice.value) : null,
    expires_at: els.mExpires.value.trim() || null,
    search_term: els.mTerm.value.trim(),
    url: els.mUrl.value.trim() || null,
    location: els.mLocation.value.trim() || null,
    description: els.mDescription.value.trim() || null,
    source: els.mSection.value === "farmacia" ? "manual" : "facebook",
  };
  els.manualStatus.textContent = "Salvando...";
  try {
    const item = await postJSON("/api/manual", payload);
    els.manualStatus.textContent = `Salvo: ${item.label || "item registrado"}${item.expiry ? ` · ${item.expiry.text}` : ""}`;
    els.manualForm.reset();
    state.section = payload.section;
    state.selectedTerm = payload.search_term;
    applySectionUI();
    await refreshAll();
  } catch (err) {
    els.manualStatus.textContent = `Erro: ${err.message}`;
  }
});

els.searchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = els.query.value.trim();
  const onlyPoa = els.onlyPoa.checked;
  els.searchStatus.textContent = "Buscando na OLX...";
  try {
    const data = await postJSON("/api/search", {
      query,
      max_pages: parseInt(els.maxPages.value, 10),
      only_poa_metro: onlyPoa,
    });
    els.searchStatus.textContent = `${data.count} anúncios encontrados/atualizados para "${query}".`;
    state.selectedTerm = query;
    await refreshAll();
  } catch (err) {
    els.searchStatus.textContent = `Erro: ${err.message}`;
  }
});

/* ---------- Inicio ---------- */

async function init() {
  try {
    const cfg = await api("/api/config");
    state.liveSearch = cfg.live_search;
  } catch (_) {
    state.liveSearch = false;
  }
  applySectionUI();
  updateQuickLinks();
  await refreshAll();
  await loadSyncStatus();
  setInterval(loadSyncStatus, 20000);
}

init();
