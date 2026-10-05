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
  textBtn: $("text-btn"),
  dropzone: $("dropzone"),
  imageInput: $("image-input"),
  ocrStatus: $("ocr-status"),
  recentCaptures: $("recent-captures"),
  cartCard: $("cart-card"),
  cartLines: $("cart-lines"),
  cartTotals: $("cart-totals"),
  cartWarnings: $("cart-warnings"),
  cartClear: $("cart-clear"),
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
  renderCart();
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
    .filter((i) => !(i.promo && i.promo.level === "encerrada"))
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
  if (item.promo) {
    const cls = { urgente: "warn", ativa: "ok", encerrada: "expired" }[item.promo.level] || "ok";
    children.push(el("span", { class: `badge ${cls}`, text: `⏱ ${item.promo.text}` }));
  }
  return el("td", { "data-label": "Preço" }, children);
}

const PRAZO_OPTIONS = [
  { value: "", label: "Definir prazo…" },
  { value: "1", label: "+1 h" },
  { value: "2", label: "+2 h" },
  { value: "6", label: "+6 h" },
  { value: "24", label: "+24 h" },
  { value: "eod", label: "Até 23h59 de hoje" },
  { value: "clear", label: "Sem prazo" },
];

function prazoValue(option) {
  if (option === "clear") return null;
  if (option === "eod") {
    const d = new Date();
    d.setHours(23, 59, 0, 0);
    return d.toISOString();
  }
  return new Date(Date.now() + Number(option) * 3600 * 1000).toISOString();
}

function buildPrazoSelect(item) {
  const select = el("select", { class: "prazo-select", "aria-label": "Prazo da promoção" });
  for (const o of PRAZO_OPTIONS) {
    select.appendChild(el("option", { value: o.value, text: o.label }));
  }
  select.addEventListener("change", async () => {
    const opt = select.value;
    if (!opt) return;
    try {
      await api(`/api/listings/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ promo_ends_at: prazoValue(opt) }),
      });
      await loadListings();
    } catch (err) {
      els.count.textContent = `Erro: ${err.message}`;
    }
  });
  return select;
}

function toggleCart(item) {
  const cart = loadCart();
  const idx = cart.findIndex((c) => c.id === item.id);
  if (idx >= 0) cart.splice(idx, 1);
  else cart.push({ id: item.id, qty: 1 });
  saveCart(cart);
  loadListings();
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

  const extras = [];
  if (state.section === "farmacia") {
    const inCart = loadCart().some((c) => c.id === item.id);
    const cartBtn = el("button", {
      type: "button",
      class: `icon-btn${inCart ? " in-cart" : ""}`,
      title: inCart ? "Tirar da compra" : "Adicionar à compra",
      text: inCart ? "✓ na compra" : "+ compra",
    });
    cartBtn.addEventListener("click", () => toggleCart(item));
    extras.push(buildPrazoSelect(item), cartBtn);
  }

  return el("td", { class: "actions", "data-label": "Ações" }, [...extras, histBtn, hideBtn, delBtn]);
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

/* ---------- Farmacia: registrar por print (OCR no navegador) ---------- */

const KNOWN_TERMS = [
  "fralda", "lenco umedecido", "dipirona", "paracetamol", "ibuprofeno",
  "soro fisiologico", "vitamina", "pomada", "shampoo", "sabonete", "protetor solar",
];

function searchTermFor(title) {
  const norm = title.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const known = KNOWN_TERMS.find((t) => norm.includes(t));
  if (known) return known;
  const first = norm.match(/[a-z]{3,}/);
  return first ? first[0] : "farmacia";
}

let tesseractPromise = null;
function loadTesseract() {
  if (!tesseractPromise) {
    tesseractPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js";
      script.onload = () => resolve(window.Tesseract);
      script.onerror = () => {
        tesseractPromise = null;
        reject(new Error("Não consegui carregar o leitor de imagem. Verifique sua conexão."));
      };
      document.head.appendChild(script);
    });
  }
  return tesseractPromise;
}

async function readImageText(file) {
  const Tesseract = await loadTesseract();
  const worker = await Tesseract.createWorker("por");
  try {
    const { data } = await worker.recognize(file);
    return data.text || "";
  } finally {
    await worker.terminate();
  }
}

function renderCapture(entry) {
  const row = el("div", { class: "capture" }, [
    el("div", { class: "capture-main" }, [
      el("strong", { text: entry.title }),
      el("span", { class: "muted", text: `${formatPrice(entry.price)}${entry.old_price ? ` (antes ${formatPrice(entry.old_price)})` : ""}${entry.expires_at ? ` · validade ${entry.expires_at}` : ""}` }),
    ]),
  ]);
  const undo = el("button", { type: "button", class: "icon-btn danger", text: "Desfazer" });
  undo.addEventListener("click", async () => {
    try {
      await api(`/api/listings/${entry.id}`, { method: "DELETE" });
      row.remove();
      await refreshAll();
    } catch (err) {
      els.ocrStatus.textContent = `Erro ao desfazer: ${err.message}`;
    }
  });
  row.appendChild(undo);
  els.recentCaptures.prepend(row);
}

async function registerPromoText(text, sourceLabel) {
  const parsed = await postJSON("/api/parse-promo", { text });
  if (!parsed.title || parsed.price === null) {
    els.ocrStatus.textContent = `Não consegui achar produto e preço${sourceLabel ? ` em ${sourceLabel}` : ""}. Tente um print mais nítido ou use "colar o texto".`;
    return null;
  }
  const item = await postJSON("/api/manual", {
    section: "farmacia",
    title: parsed.title,
    price: parsed.price,
    old_price: parsed.old_price,
    expires_at: parsed.expires_at,
    promo_ends_at: parsed.promo_ends_at,
    search_term: searchTermFor(parsed.title),
    url: `manual://farmacia/promo/${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    description: text.slice(0, 500),
    source: "print",
  });
  const notes = parsed.warnings.length ? ` Atenção: ${parsed.warnings.join(" ")}` : "";
  els.ocrStatus.textContent = `Registrado: ${item.title} · ${formatPrice(item.price)}.${notes}`;
  renderCapture(item);
  state.section = "farmacia";
  state.selectedTerm = "";
  applySectionUI();
  await refreshAll();
  return item;
}

async function handleImage(file) {
  if (!file || !file.type.startsWith("image/")) {
    els.ocrStatus.textContent = "Escolha ou cole uma imagem (print ou foto).";
    return;
  }
  els.ocrStatus.textContent = "Lendo a imagem... (a primeira vez demora um pouco mais)";
  try {
    const text = await readImageText(file);
    if (!text.trim()) {
      els.ocrStatus.textContent = "Não consegui ler texto nessa imagem. Tente um print mais nítido.";
      return;
    }
    await registerPromoText(text, "essa imagem");
  } catch (err) {
    els.ocrStatus.textContent = `Erro: ${err.message}`;
  }
}

els.dropzone.addEventListener("click", () => els.imageInput.click());
els.dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") els.imageInput.click();
});
els.imageInput.addEventListener("change", () => {
  handleImage(els.imageInput.files[0]);
  els.imageInput.value = "";
});

document.addEventListener("paste", (e) => {
  if (state.section !== "farmacia") return;
  const items = Array.from(e.clipboardData?.items || []);
  const img = items.find((i) => i.type.startsWith("image/"));
  if (img) {
    e.preventDefault();
    handleImage(img.getAsFile());
  }
});

["dragover", "dragenter"].forEach((ev) => els.dropzone.addEventListener(ev, (e) => {
  e.preventDefault();
  els.dropzone.classList.add("drag");
}));
["dragleave", "drop"].forEach((ev) => els.dropzone.addEventListener(ev, () => els.dropzone.classList.remove("drag")));
els.dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  handleImage(e.dataTransfer.files[0]);
});

els.textBtn.addEventListener("click", async () => {
  const text = els.pasteText.value.trim();
  if (!text) {
    els.ocrStatus.textContent = "Cole o texto da promoção primeiro.";
    return;
  }
  try {
    await registerPromoText(text, "esse texto");
    els.pasteText.value = "";
  } catch (err) {
    els.ocrStatus.textContent = `Erro: ${err.message}`;
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

/* ---------- Minha compra ---------- */

const CART_KEY = "resale-cart";

function loadCart() {
  try {
    const raw = localStorage.getItem(CART_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

function saveCart(cart) {
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
  } catch (_) {
    // armazenamento indisponivel: a lista so dura a sessao
  }
}

async function renderCart() {
  const cart = loadCart();
  els.cartCard.hidden = state.section !== "farmacia" || cart.length === 0;
  if (els.cartCard.hidden) return;

  const ids = cart.map((c) => c.id);
  let items = [];
  try {
    const data = await api(`/api/listings/batch?ids=${ids.join(",")}`);
    items = data.items;
  } catch (err) {
    els.cartWarnings.textContent = `Erro ao carregar a compra: ${err.message}`;
    return;
  }
  const byId = new Map(items.map((i) => [i.id, i]));

  els.cartLines.replaceChildren();
  const warnings = [];
  let total = 0;
  let normal = 0;

  for (const entry of cart) {
    const item = byId.get(entry.id);
    if (!item) {
      warnings.push("Um item da lista não existe mais e foi ignorado.");
      continue;
    }
    const qtyInput = el("input", { type: "number", min: "1", value: String(entry.qty), class: "qty", "aria-label": "Quantidade" });
    qtyInput.addEventListener("change", () => {
      const q = Math.max(1, parseInt(qtyInput.value, 10) || 1);
      const updated = loadCart().map((c) => (c.id === entry.id ? { ...c, qty: q } : c));
      saveCart(updated);
      renderCart();
    });
    const removeBtn = el("button", { type: "button", class: "icon-btn danger", text: "remover" });
    removeBtn.addEventListener("click", () => toggleCart(item));

    const lineTotal = item.price * entry.qty;
    const lineNormal = (item.old_price && item.old_price > item.price ? item.old_price : item.price) * entry.qty;
    total += lineTotal;
    normal += lineNormal;

    els.cartLines.appendChild(el("div", { class: "capture" }, [
      el("div", { class: "capture-main" }, [
        el("strong", { text: item.title }),
        el("span", { class: "muted", text: `${formatPrice(item.price)} × ${entry.qty} = ${formatPrice(lineTotal)}` }),
      ]),
      el("div", { class: "row-between" }, [qtyInput, removeBtn]),
    ]));

    if (item.promo && item.promo.level === "encerrada") {
      warnings.push(`${item.title}: promoção encerrada, confira o preço antes de comprar.`);
    } else if (item.promo && item.promo.level === "urgente") {
      warnings.push(`${item.title}: ${item.promo.text}.`);
    }
    if (item.expiry && item.expiry.level === "vencido") {
      warnings.push(`${item.title}: produto vencido.`);
    }
  }

  const saving = normal - total;
  els.cartTotals.replaceChildren(
    el("div", { class: "total-line" }, [el("span", { text: "Total" }), el("strong", { text: formatPrice(total) })]),
    el("div", { class: "total-line muted" }, [el("span", { text: "Preço normal" }), el("span", { text: formatPrice(normal) })]),
    el("div", { class: "total-line good" }, [el("span", { text: "Você economiza" }), el("strong", { text: formatPrice(Math.max(0, saving)) })]),
  );
  els.cartWarnings.textContent = warnings.join(" ");
}

els.cartClear.addEventListener("click", () => {
  saveCart([]);
  loadListings();
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
  setInterval(() => {
    if (state.section === "farmacia" && document.visibilityState === "visible") loadListings();
  }, 60000);
}

init();
