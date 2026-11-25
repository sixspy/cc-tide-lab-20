async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url + " " + r.status);
  return r.json();
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? "{}" : JSON.stringify(body),
  });
  const t = await r.text();
  let data;
  try { data = JSON.parse(t); } catch { data = { 原文: t }; }
  if (!r.ok) throw new Error((data && (data.错误 || data.detail)) || t || String(r.status));
  return data;
}
function 行(html) {
  const tr = document.createElement("tr");
  tr.innerHTML = html;
  return tr;
}
function 徽章(文, 类) {
  return `<span class="徽章 ${类 || ""}">${文}</span>`;
}
function 空态(文) {
  return `<p class="说明条">${文}</p>`;
}
function 格式概览(o) {
  return [
    ["观测点", o["观测点"] || 0],
    ["在缓冲", o["在缓冲"] || 0],
    ["窗切片", o["窗切片"] || 0],
    ["迟到", o["迟到"] || 0],
  ];
}
function 渲染水位(el, overview) {
  if (!el) return;
  el.innerHTML = "";
  for (const [标, 值] of 格式概览(overview || {})) {
    const d = document.createElement("div");
    d.className = "水卡";
    d.innerHTML = `<div class="数">${值}</div><div class="标">${标}</div>`;
    el.appendChild(d);
  }
}
function 窗规一行(rules) {
  if (!rules) return "窗规未加载";
  return `${rules["当前窗号"] || "?"} · ${rules["窗起"] || ""} → ${rules["窗止"] || ""} · 窗长秒 ${rules["窗长秒"] || "?"}`;
}
function 装载摘要(report) {
  if (!report) return "";
  return `入流 ${report["入流"] || 0} / 入缓冲 ${report["入缓冲"] || 0} / 迟到 ${report["迟到"] || 0} / 驳回 ${report["驳回"] || 0}`;
}
function 关窗摘要(report) {
  if (!report) return "";
  return `窗 ${report["窗号"] || "?"} · 成片 ${report["成片数"] || 0} · 缓冲消耗 ${report["缓冲消耗"] || 0}`;
}
function 贯验摘要(report) {
  if (!report) return "";
  return `${report["是否对齐"] ? "对齐" : "撕裂"} · 在缓冲 ${report["在缓冲"]} · 切片事件 ${report["切片事件"]} · 迟到 ${report["迟到"]}`;
}
function 安全文本(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

// ---- 观测点换绑：四字段契约（旧键/新键/拒因或归档键/valid）----
function valid徽章(v) {
  return v ? 徽章("valid · 有效", "好") : 徽章("invalid", "危");
}
function 换绑记录单元格(r) {
  const disp = r["拒因或归档键"] || r["拒因"] || r["归档键"] || "";
  const fp = r["指纹"] ? String(r["指纹"]).slice(0, 12) + "…" : "";
  return `
    <td>${安全文本(r["旧键"])}</td>
    <td>${安全文本(r["新键"])}</td>
    <td>${安全文本(r["形态"] || "")}</td>
    <td title="${安全文本(r["拒因或归档键"] || "")}">${安全文本(disp)}</td>
    <td title="${安全文本(r["指纹"] || "")}">${安全文本(fp)}</td>
    <td>${valid徽章(!!r["valid"])}</td>`;
}
async function 刷新换绑账(tbId, stratId) {
  let view = null;
  try { view = await getJSON("/api/观测点换绑"); } catch (e) { return null; }
  const recs = view["记录"] || (Array.isArray(view) ? view : []);
  const tb = document.getElementById(tbId || "换绑账");
  if (tb) {
    tb.innerHTML = "";
    if (!recs.length) {
      tb.innerHTML = `<tr><td colspan="6">${空态("尚无换绑账。可在下方执行一次运单键换绑。")}</td></tr>`;
    }
    for (const r of recs.slice().reverse()) tb.appendChild(行(换绑记录单元格(r)));
  }
  const st = document.getElementById(stratId || "换绑策略");
  if (st && view && !Array.isArray(view)) {
    const cur = (view["现行键集合"] || []).join("、") || "∅";
    const arc = (view["归档键集合"] || []).join("、") || "∅";
    st.textContent = `当前形态：${view["当前策略"] || view["策略"] || "?"}　｜　现行缓冲键集合：${cur}　｜　归档键：${arc}`;
  }
  return view;
}
function 挂载换绑面板(opts) {
  opts = opts || {};
  const ids = Object.assign({
    tbody: "换绑账", strategy: "换绑策略", btn: "换绑钮",
    receipt: "换绑回执", old: "换旧", neu: "换新", mode: "换形态",
  }, opts.ids || {});
  async function 刷() {
    await 刷新换绑账(ids.tbody, ids.strategy);
    if (typeof opts.after === "function") { try { await opts.after(); } catch (e) {} }
  }
  const btn = document.getElementById(ids.btn);
  if (btn) {
    btn.onclick = async () => {
      const out = document.getElementById(ids.receipt);
      const 旧 = (document.getElementById(ids.old) || {}).value || "";
      const 新 = (document.getElementById(ids.neu) || {}).value || "";
      const 形 = (document.getElementById(ids.mode) || {}).value || "";
      try {
        const rec = await postJSON("/api/观测点换绑", {
          "旧键": 旧.trim(), "新键": 新.trim(), "形态": 形,
        });
        if (out) out.textContent = JSON.stringify(rec, null, 2);
        await 刷();
      } catch (e) { if (out) out.textContent = String(e); }
    };
  }
  刷();
  return { 刷 };
}
window.潮切 = {
  getJSON, postJSON, 行, 徽章, 空态, 格式概览, 渲染水位,
  窗规一行, 装载摘要, 关窗摘要, 贯验摘要, 安全文本,
  valid徽章, 换绑记录单元格, 刷新换绑账, 挂载换绑面板,
};
