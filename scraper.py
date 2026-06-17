<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ボイスドラマ ランキングハブ</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@400;500&family=Noto+Sans+JP:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
    --ink:#26211f;--muted:#8a8077;--border:#e7e1d8;--border-light:#f0ebe3;
    --bg:#faf7f2;--surface:#ffffff;
}
/* サイトごとのアクセントカラー */
.site-garu{--accent-50:#fff1f4;--accent-100:#fde0e7;--accent-600:#d4386f;--accent-800:#8b1a42;--accent-muted:#b8829a;--accent-sub:#8b4f6a;}
.site-stella{--accent-50:#f1efff;--accent-100:#e1ddff;--accent-600:#534ab7;--accent-800:#26215c;--accent-muted:#9a93c9;--accent-sub:#534ab7;}
.site-poke{--accent-50:#f0f4ff;--accent-100:#e0e9ff;--accent-600:#4361c2;--accent-800:#1e3a8a;--accent-muted:#8a9ad0;--accent-sub:#4a5fa8;}

*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Noto Sans JP',sans-serif;background:var(--bg);color:var(--ink);min-height:100vh}
.hub-wrap{max-width:1200px;margin:0 auto;padding:20px 16px 60px}

.hub-header{display:flex;align-items:center;gap:14px;padding:16px 24px;background:var(--surface);border:0.5px solid var(--border);border-radius:16px;margin-bottom:16px}
.hub-icon{width:38px;height:38px;border-radius:50%;background:#f3eee5;display:flex;align-items:center;justify-content:center;font-size:18px}
.hub-title{font-family:'Noto Serif JP',serif;font-size:18px;font-weight:500;color:var(--ink);letter-spacing:.04em}
.hub-sub{font-size:12px;font-weight:500;color:var(--muted);margin-top:3px}
.hub-update{margin-left:auto;font-size:11px;color:var(--muted);background:var(--bg);border:0.5px solid var(--border);border-radius:20px;padding:5px 12px;white-space:nowrap}

.site-tabs{display:flex;gap:6px;margin-bottom:20px;flex-wrap:wrap}
.site-tab{display:flex;align-items:center;gap:7px;padding:9px 18px;border-radius:20px;font-size:13px;font-weight:500;border:0.5px solid var(--border);color:var(--muted);background:var(--surface);cursor:pointer;transition:all .15s}
.site-tab:hover{background:var(--border-light)}
.site-tab.active{color:#fff;border-color:transparent}
.site-tab.active.site-garu{background:#d4386f}
.site-tab.active.site-stella{background:#534ab7}
.site-tab.active.site-poke{background:#4361c2}
.site-tab .tab-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}

.site-panel{display:none}
.site-panel.active{display:block}

.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px}
.stat-card{background:var(--surface);border:0.5px solid var(--border);border-radius:14px;padding:14px 16px}
.stat-label{font-size:11px;color:var(--muted);margin-bottom:6px}
.stat-value{font-family:'Noto Serif JP',serif;font-size:26px;font-weight:500;color:var(--accent-800)}
.stat-sub{font-size:10px;color:var(--muted);margin-top:3px}

.section{margin-bottom:28px}
.section-head{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.section-title{font-family:'Noto Serif JP',serif;font-size:15px;font-weight:500;color:var(--accent-800)}
.section-badge{font-size:10px;background:var(--accent-100);color:var(--accent-600);border:0.5px solid var(--border);border-radius:20px;padding:2px 9px}

.table-card{background:var(--surface);border:0.5px solid var(--border);border-radius:16px;overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}
thead th{background:#fafafa;color:var(--accent-800);font-weight:500;padding:10px 8px;border-bottom:0.5px solid var(--border-light);text-align:left;font-size:11px}
tbody td{padding:6px 8px;border-bottom:0.5px solid var(--border-light);vertical-align:top}
tbody td.thumb-wrap{vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--accent-50)}

.rb{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;font-size:11px;font-weight:500}
.r1{background:#fef3c7;color:#92400e;border:0.5px solid #fde68a}
.r2{background:#f1f5f9;color:#475569;border:0.5px solid #e2e8f0}
.r3{background:#fef0e6;color:#9a3412;border:0.5px solid #fed7aa}
.rn{background:var(--accent-50);color:var(--accent-muted);border:0.5px solid var(--border-light)}

.thumb-wrap{width:150px;min-width:150px;padding:4px 6px 4px 8px;position:relative}
.thumb-wrap img{width:146px;height:110px;object-fit:cover;border-radius:8px;border:0.5px solid var(--border-light);display:block}
.thumb-wrap a{display:block}
.thumb-rank{position:absolute;top:7px;left:11px;z-index:1}
.no-thumb{width:146px;height:110px;border-radius:8px;background:var(--accent-100);display:flex;align-items:center;justify-content:center;font-size:28px;border:0.5px solid var(--border-light)}

.title-cell{padding-left:8px !important}
.work-title{font-weight:500;color:var(--accent-800);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.work-title a{color:var(--accent-800);text-decoration:none}
.work-title a:hover{color:var(--accent-600);text-decoration:underline}
.work-circle{font-size:10px;color:var(--muted);margin-top:2px}
.genres{display:flex;flex-wrap:wrap;gap:3px;margin-top:3px}
.gtag{display:inline-block;font-size:9px;background:var(--accent-50);color:var(--accent-muted);border:0.5px solid var(--border-light);border-radius:20px;padding:1px 6px;white-space:nowrap}

.rise-pill{display:inline-flex;align-items:center;gap:2px;background:var(--accent-50);color:var(--accent-600);border:0.5px solid var(--border);border-radius:20px;padding:3px 8px;font-size:11px;font-weight:500}
.tup{font-size:11px;font-weight:500;color:#be123c}
.tdn{font-size:11px;font-weight:500;color:#0369a1}
.tsm{font-size:11px;color:var(--muted)}
.tnew{display:inline-flex;align-items:center;gap:2px;background:#ecfdf5;color:#065f46;border:0.5px solid #6ee7b7;border-radius:20px;padding:2px 7px;font-size:10px;font-weight:500}
.chart-cell{width:220px}
.chart-wrap{width:100%;height:80px}
.no-data{font-size:11px;color:var(--muted)}
.empty-msg{text-align:center;padding:24px;color:var(--muted);font-size:12px}
.loading-msg{text-align:center;padding:40px;color:var(--muted);font-size:13px}
.error-msg{text-align:center;padding:24px;color:#9a3412;font-size:12px;background:#fff7ed;border-radius:12px}

.hub-footer{text-align:center;margin-top:40px;font-size:11px;color:var(--muted);padding-top:20px;border-top:0.5px solid var(--border-light)}

@media (max-width:640px){
    .hub-wrap{padding:10px 8px 40px}
    .hub-header{padding:10px 12px;gap:8px;flex-wrap:wrap}
    .hub-title{font-size:14px}
    .hub-sub{font-size:10px}
    .hub-update{font-size:9px;padding:3px 8px;margin-left:0;width:100%}
    .site-tab{font-size:12px;padding:7px 12px}
    .stat-row{gap:5px}
    .stat-card{padding:8px 6px}
    .stat-value{font-size:18px}
    .stat-label{font-size:8px}
    .stat-sub{font-size:7px}
    .table-card{overflow:visible}
    table{display:block}
    thead{display:none}
    tbody{display:flex;flex-direction:column;gap:6px;padding:6px}
    tbody tr{display:grid;grid-template-columns:110px 1fr;grid-template-rows:auto auto auto;background:var(--surface);border:0.5px solid var(--border);border-radius:10px;overflow:hidden;padding:0}
    tbody td{border-bottom:none;padding:0;width:auto !important}
    tbody tr:hover td{background:transparent}
    .thumb-wrap{grid-column:1;grid-row:1/4;width:110px !important;min-width:110px;padding:6px 4px 6px 6px;position:relative}
    .thumb-wrap img,.no-thumb{width:100px;height:75px;border-radius:6px}
    .thumb-rank{top:9px;left:9px}
    .title-cell{grid-column:2;grid-row:1;padding:6px 8px 2px 4px !important;display:block}
    .work-title{font-size:11px;white-space:normal;line-height:1.3}
    .chart-cell{grid-column:1/3;grid-row:4;width:100% !important}
    .chart-wrap{height:72px;padding:0 4px 6px;display:block}
    .section-title{font-size:13px}
    .section{margin-bottom:20px}
}
</style>
</head>
<body>
<div class="hub-wrap">

<div class="hub-header">
    <div class="hub-icon">🎧</div>
    <div>
        <div class="hub-title">乙女向けボイス・ASMR作品 ランキング</div>
    </div>
    <div class="hub-update" id="hub-update">🔄 毎日23:30頃更新 ／ ―</div>
</div>

<div class="site-tabs" id="site-tabs">
    <button class="site-tab active site-garu" data-site="garu">
        <span class="tab-dot" style="background:#d4386f"></span>がるまに
    </button>
    <button class="site-tab site-stella" data-site="stella">
        <span class="tab-dot" style="background:#534ab7"></span>ステラプレイヤー
    </button>
    <button class="site-tab site-poke" data-site="poke">
        <span class="tab-dot" style="background:#4361c2"></span>ポケドラ
    </button>
</div>

<div id="panels"></div>

<div class="hub-footer">
    各サイトのデータを直接取得して表示しています。更新頻度は各サイトの仕様に準じます。
</div>

</div>

<script>
/* ===========================================
   データソース設定
   =========================================== */
const SOURCES = {
    garu: {
        url: "https://garumaninow.onrender.com/api/ranking",
        label: "DLsiteがるまに ランキング分析",
        sub: "乙女向けボイス・ASMR作品データ",
        accentClass: "site-garu",
        statLabels: ["📦 収録作品数", "✨ 新着", "📈 急上昇作品"],
    },
    stella: {
        url: "https://jikaseiorangette.github.io/stellaplayer-ranking/data/ranking.json",
        label: "ステラプレイヤー ランキング分析",
        sub: "オトメ向けボイス・音声作品データ",
        accentClass: "site-stella",
        statLabels: ["📦 収録作品数", "✨ 新着", "🔔 近日配信予定"],
    },
    poke: {
        url: "https://jikaseiorangette.github.io/pokedora-ranking/data/latest_adt.json",
        metaUrl: "https://jikaseiorangette.github.io/pokedora-ranking/data/meta_adt.json",
        label: "ポケドラ ランキング分析",
        sub: "ドラマCD人気作品データ",
        accentClass: "site-poke",
        statLabels: ["📦 収録作品数", "✨ 新着", "📈 急上昇作品"],
    },
};

const cache = {};

/* ===========================================
   各サイトのレスポンスを共通フォーマットに正規化
   common item shape:
   { id, title, sub, url, img, tags:[], rankChange:null|num, isNew:bool, rank }
   =========================================== */

function normalizeGaru(data) {
    const ranking = (data.ranking || []).map(r => ({
        id: r.work_id,
        title: r.title,
        sub: r.voice_actor || "",
        url: r.affiliate_url || "#",
        img: r.thumb_url || "",
        tags: (r.genre || "").split(",").map(s => s.trim()).filter(Boolean).slice(0, 4),
        rank: r.rank,
        rankChange: r.is_new ? null : (r.rank_change || 0),
        isNew: !!r.is_new,
    }));
    const rising = (data.rising || []).map(r => ({
        id: r.work_id, title: r.title, sub: r.voice_actor || "",
        url: r.affiliate_url || "#", img: r.thumb_url || "",
        tags: (r.genre || "").split(",").map(s => s.trim()).filter(Boolean).slice(0, 4),
        rank: r.rank, rise: r.rise,
    }));
    return {
        stats: [data.total_works ?? "—", data.new_today ?? "—", data.rising_count ?? "—"],
        ranking, rising, preorders: [],
        graphData: data.graph_data || {},
        updated: data.today_str || "",
    };
}

function normalizeStella(data) {
    const items = (data.categories && data.categories.GIRLS) || [];
    const ranking = items.map(it => ({
        id: it.product_id,
        title: it.title,
        sub: it.cv || "",
        url: it.link || "#",
        img: it.img || "",
        tags: (it.tags || []).slice(0, 4),
        rank: it.rank,
        rankChange: it.prev_rank ? (it.prev_rank - it.rank) : null,
        isNew: !it.prev_rank,
    }));
    const preorders = (data.preorders || []).slice(0, 2).map(p => ({
        id: p.id, title: p.title, sub: p.cv || "",
        url: `https://www.stellaplayer.jp/product/${p.id}`, img: p.img || "",
        tags: (p.tags || []).slice(0, 4),
        releaseDate: p.release_date || "", streamDate: p.streaming_date || "",
        circle: p.circle || "",
    }));
    const graphData = {};
    items.forEach(it => {
        const hist = it.history || [];
        graphData[it.product_id] = {
            labels: hist.map(h => h.date),
            ranks: hist.map(h => h.rank),
        };
    });
    return {
        stats: [data.total_products ?? "—", "—", (data.preorders || []).length || "—"],
        ranking, rising: [], preorders,
        graphData,
        updated: data.updated || "",
    };
}

function normalizePoke(items, meta) {
    items = Array.isArray(items) ? items : [];
    meta = meta || {};
    const ranking = items.map(it => ({
        id: it.product_id,
        title: it.title,
        sub: it.voice_actor || "",
        url: it.work_url || "#",
        img: it.thumb_url || "",
        tags: (it.tags || []).slice(0, 4),
        rank: it.rank,
        rankChange: null,
        isNew: false,
    }));
    return {
        stats: [
            meta.total_works ?? (items.length || "—"),
            meta.new_today ?? "—",
            meta.rising_count ?? "—",
        ],
        ranking, rising: [], preorders: [],
        graphData: {},
        updated: meta.updated || "",
    };
}

function normalize(siteKey, rawData, meta) {
    if (siteKey === "garu") return normalizeGaru(rawData);
    if (siteKey === "stella") return normalizeStella(rawData);
    if (siteKey === "poke") return normalizePoke(rawData, meta);
    return { stats: ["—","—","—"], ranking: [], rising: [], preorders: [], graphData: {}, updated: "" };
}

/* ===========================================
   HTML生成ヘルパー
   =========================================== */

function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function rankBadgeClass(rank) {
    if (rank === 1) return "r1";
    if (rank === 2) return "r2";
    if (rank === 3) return "r3";
    return "rn";
}

function thumbHtml(item) {
    if (item.img) {
        return `<img src="${esc(item.img)}" alt="" loading="lazy" onerror="this.outerHTML='<div class=&quot;no-thumb&quot;>🎧</div>'">`;
    }
    return `<div class="no-thumb">🎧</div>`;
}

function tagsHtml(tags) {
    if (!tags || !tags.length) return "";
    return `<div class="genres">${tags.map(t => `<span class="gtag">${esc(t)}</span>`).join("")}</div>`;
}

function changeHtml(item) {
    if (item.isNew) return `<span class="tnew">🆕 新着</span>`;
    const c = item.rankChange;
    if (c === null || c === undefined) return `<span class="tsm">－</span>`;
    if (c > 0) return `<span class="tup">▲${c}</span>`;
    if (c < 0) return `<span class="tdn">▼${Math.abs(c)}</span>`;
    return `<span class="tsm">－</span>`;
}

function rankRow(item, canvasId) {
    const rb = `<span class="rb ${rankBadgeClass(item.rank)}">${item.rank}</span>`;
    return `<tr>
        <td class="thumb-wrap">
            <span class="thumb-rank">${rb}</span>
            <a href="${esc(item.url)}" target="_blank" rel="noopener">${thumbHtml(item)}</a>
        </td>
        <td class="title-cell">
            <div class="work-title"><a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a></div>
            <div class="work-circle">${esc(item.sub)}</div>
            ${tagsHtml(item.tags)}
        </td>
        <td style="font-size:11px;color:var(--accent-sub)">${esc(item.sub)}</td>
        <td>${changeHtml(item)}</td>
        <td class="chart-cell"><canvas id="${canvasId}" class="chart-wrap" data-id="${esc(item.id)}"></canvas></td>
    </tr>`;
}

function risingRow(item, canvasId) {
    const rb = `<span class="rb ${rankBadgeClass(item.rank)}">${item.rank}</span>`;
    return `<tr>
        <td class="thumb-wrap">
            <span class="thumb-rank">${rb}</span>
            <a href="${esc(item.url)}" target="_blank" rel="noopener">${thumbHtml(item)}</a>
        </td>
        <td class="title-cell">
            <div class="work-title"><a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a></div>
            <div class="work-circle">${esc(item.sub)}</div>
            ${tagsHtml(item.tags)}
        </td>
        <td style="font-size:11px;color:var(--accent-sub)">${esc(item.sub)}</td>
        <td><span class="rise-pill">▲${item.rise}位UP</span></td>
        <td class="chart-cell"><canvas id="${canvasId}" class="chart-wrap" data-id="${esc(item.id)}"></canvas></td>
    </tr>`;
}

function preorderRow(item, index) {
    const rb = `<span class="rb rn">${index + 1}</span>`;
    const dateLine = item.streamDate ? `<span style="color:var(--accent-600);margin-right:6px">配信開始: ${esc(item.streamDate)}</span>` : "";
    return `<tr>
        <td class="thumb-wrap">
            <span class="thumb-rank">${rb}</span>
            <a href="${esc(item.url)}" target="_blank" rel="noopener">${thumbHtml(item)}</a>
        </td>
        <td class="title-cell">
            <div class="work-title"><a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a></div>
            <div class="work-circle">${dateLine}${esc(item.circle || "")}</div>
            ${tagsHtml(item.tags)}
        </td>
        <td style="font-size:11px;color:var(--accent-sub)">${esc(item.sub)}</td>
        <td style="font-size:12px;color:var(--accent-800);font-weight:500">${esc(item.releaseDate || "")}</td>
    </tr>`;
}

/* ===========================================
   パネル全体のレンダリング
   =========================================== */

function renderPanel(siteKey, norm) {
    const src = SOURCES[siteKey];
    const top10 = norm.ranking.slice(0, 10);

    let preorderSection = "";
    if (norm.preorders && norm.preorders.length) {
        preorderSection = `<div class="section">
            <div class="section-head">
                <span style="font-size:16px">🔔</span>
                <span class="section-title">近日配信予定</span>
                <span class="section-badge">データあり・配信開始前</span>
            </div>
            <div class="table-card"><table>
                <colgroup><col style="width:150px"><col style="width:auto"><col style="width:10%"><col style="width:12%"></colgroup>
                <thead><tr><th></th><th>タイトル / サークル</th><th>声優</th><th>発売予定日</th></tr></thead>
                <tbody>${norm.preorders.map((p, i) => preorderRow(p, i)).join("")}</tbody>
            </table></div>
        </div>`;
    }

    let risingSection = "";
    if (norm.rising && norm.rising.length) {
        risingSection = `<div class="section">
            <div class="section-head">
                <span style="font-size:16px">🔥</span>
                <span class="section-title">急上昇作品</span>
                <span class="section-badge">前日比上昇</span>
            </div>
            <div class="table-card"><table>
                <colgroup><col style="width:150px"><col style="width:auto"><col style="width:10%"><col style="width:8%"><col style="width:26%"></colgroup>
                <thead><tr><th></th><th>タイトル / サークル</th><th>声優</th><th>上昇幅</th><th class="chart-cell">推移グラフ</th></tr></thead>
                <tbody>${norm.rising.map((r, i) => risingRow(r, `${siteKey}_rc_${i+1}`)).join("")}</tbody>
            </table></div>
        </div>`;
    }

    const rankingRows = top10.length
        ? top10.map((r, i) => rankRow(r, `${siteKey}_wc_${i+1}`)).join("")
        : `<tr><td colspan="5" class="empty-msg">データがありません</td></tr>`;

    return `
    <div class="stat-row">
        <div class="stat-card">
            <div class="stat-label">${src.statLabels[0]}</div>
            <div class="stat-value">${esc(norm.stats[0])}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">${src.statLabels[1]}</div>
            <div class="stat-value">${esc(norm.stats[1])}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">${src.statLabels[2]}</div>
            <div class="stat-value">${esc(norm.stats[2])}</div>
        </div>
    </div>

    ${preorderSection}
    ${risingSection}

    <div class="section">
        <div class="section-head">
            <span style="font-size:16px">🏆</span>
            <span class="section-title">本日のランキング</span>
            <span class="section-badge">TOP 10</span>
        </div>
        <div class="table-card"><table>
            <colgroup><col style="width:150px"><col style="width:auto"><col style="width:10%"><col style="width:7%"><col style="width:26%"></colgroup>
            <thead><tr><th></th><th>タイトル / サークル</th><th>声優</th><th>推移</th><th class="chart-cell">推移グラフ</th></tr></thead>
            <tbody>${rankingRows}</tbody>
        </table></div>
    </div>`;
}

/* ===========================================
   グラフ描画
   =========================================== */

function drawChart(canvasId, itemId, graphData, accentHex) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    const d = graphData[itemId];
    if (!d || !d.ranks || !d.ranks.length) {
        ctx.parentElement.innerHTML = '<span class="no-data">データ蓄積中</span>';
        return;
    }
    const disp = d.ranks.map(v => (v === null || v === undefined) ? null : (v > 14 ? 15 : v));
    const isSingle = d.ranks.filter(v => v !== null && v !== undefined).length === 1;
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: d.labels,
            datasets: [{
                data: disp,
                borderColor: accentHex,
                backgroundColor: 'transparent',
                borderWidth: 1.5,
                pointRadius: isSingle ? 5 : 2,
                pointHoverRadius: 6,
                pointBackgroundColor: accentHex,
                fill: false,
                tension: 0.4,
                spanGaps: false,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 6, left: 2 } },
            interaction: { mode: 'index', intersect: false },
            scales: {
                y: {
                    reverse: true, min: -1, max: 17,
                    ticks: {
                        font: { size: 11 }, color: '#8a8077',
                        callback: v => v===1?'1位':v===5?'5位':v===10?'10位':v===15?'圏外':null
                    },
                    beforeFit: axis => {
                        axis.ticks = [{value:1,label:'1位'},{value:5,label:'5位'},{value:10,label:'10位'},{value:15,label:'圏外'}];
                    },
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    border: { display: false }
                },
                x: {
                    ticks: { font: { size: 9 }, color: '#8a8077', maxTicksLimit: 4 },
                    grid: { display: false }, border: { display: false }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: c => {
                            const raw = d.ranks[c.dataIndex];
                            if (raw === null || raw === undefined) return '';
                            return raw > 30 ? '圏外' : raw + '位';
                        }
                    },
                    titleFont: { size: 11 }, bodyFont: { size: 12 }, padding: 8,
                }
            }
        }
    });
}

const ACCENT_HEX = { garu: '#d4386f', stella: '#534ab7', poke: '#4361c2' };

/* ===========================================
   サイトの読み込み・タブ切り替え
   =========================================== */

const panelsEl = document.getElementById("panels");
const tabsEl = document.getElementById("site-tabs");

function showLoading(siteKey) {
    panelsEl.innerHTML = `<div class="loading-msg">${esc(SOURCES[siteKey].label)} を読み込み中...</div>`;
}

function showError(siteKey, err) {
    panelsEl.innerHTML = `<div class="error-msg">
        ${esc(SOURCES[siteKey].label)} のデータ取得に失敗しました。<br>
        サイトが起動中、またはネットワーク設定でブロックされている可能性があります。<br>
        <span style="font-size:10px;opacity:.7">${esc(err.message || err)}</span>
    </div>`;
}

async function loadSite(siteKey) {
    if (cache[siteKey]) {
        renderAndMount(siteKey, cache[siteKey]);
        return;
    }
    showLoading(siteKey);
    try {
        const res = await fetch(SOURCES[siteKey].url, { mode: "cors" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const raw = await res.json();

        let meta = null;
        if (SOURCES[siteKey].metaUrl) {
            try {
                const metaRes = await fetch(SOURCES[siteKey].metaUrl, { mode: "cors" });
                if (metaRes.ok) meta = await metaRes.json();
            } catch (e) {
                /* メタ情報の取得失敗は無視してランキング表示は継続 */
            }
        }

        const norm = normalize(siteKey, raw, meta);
        cache[siteKey] = norm;
        renderAndMount(siteKey, norm);
    } catch (err) {
        showError(siteKey, err);
    }
}

function updateHeaderDate(norm) {
    const el = document.getElementById("hub-update");
    if (!el) return;
    el.textContent = norm.updated
        ? `🔄 毎日23:30頃更新 ／ ${norm.updated}`
        : `🔄 毎日23:30頃更新`;
}

function renderAndMount(siteKey, norm) {
    updateHeaderDate(norm);
    const wrapper = document.createElement("div");
    wrapper.className = `site-panel active ${SOURCES[siteKey].accentClass}`;
    wrapper.innerHTML = renderPanel(siteKey, norm);
    panelsEl.innerHTML = "";
    panelsEl.appendChild(wrapper);

    const accent = ACCENT_HEX[siteKey];
    wrapper.querySelectorAll('canvas[data-id]').forEach(c => {
        drawChart(c.id, c.dataset.id, norm.graphData, accent);
    });
}

tabsEl.addEventListener("click", e => {
    const btn = e.target.closest(".site-tab");
    if (!btn) return;
    document.querySelectorAll(".site-tab").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");
    loadSite(btn.dataset.site);
});

loadSite("garu");
</script>
</body>
</html>
