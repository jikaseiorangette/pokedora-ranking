# scraper.py
# ポケドラのランキングをスクレイプし、JSONと静的HTMLを生成する

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import csv
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

def now_jst():
    return datetime.now(JST)

# 発売予定データのCSVパス（他の仕組みで取得・更新される想定）
# 必須カラム: product_id, title, voice_actor, circle, release_date, stream_date, tags, thumb_url, work_url, status
PRODUCTS_CSV = Path("data/products.csv")

CATEGORIES = {
    "adt":    ("オトナ向け", "https://pokedora.com/ranking/index.php?store=adt&term=1&age_check=1"),
    "adt-bl": ("オトナBL",   "https://pokedora.com/ranking/index.php?store=adt-bl&term=1&age_check=1"),
    "home":   ("一般",       "https://pokedora.com/ranking/index.php?store=home&term=1"),
    "bl":     ("BL",         "https://pokedora.com/ranking/index.php?store=bl&term=1"),
}

# ----------------------------------------
# スクレイピング（Playwright JS経由）
# ----------------------------------------

def fetch_ranking(page, store, url):
    print(f"  [{store}] アクセス中: {url}")
    for attempt in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            # ページを下にスクロールしてランキングを強制描画
            page.evaluate("window.scrollTo(0, 300)")
            time.sleep(3)
            page.evaluate("window.scrollTo(0, 600)")
            time.sleep(3)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(5)
            break
        except Exception as e:
            print(f"  失敗({attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(15)
            else:
                raise

    # product_idを含むリンクを直接取得
    all_anchors = page.query_selector_all("a[href*='product_id']")
    print(f"  [{store}] product_idリンク数: {len(all_anchors)}")

    # 0件なら全aタグでフォールバック
    if not all_anchors:
        all_anchors = page.query_selector_all("a")
        print(f"  [{store}] フォールバック: aタグ数: {len(all_anchors)}")

    works = []
    seen = set()

    for anchor in all_anchors:
        if len(works) >= 30:
            break
        try:
            href = anchor.get_attribute("href") or ""
            if not href:
                continue
            # product_idを抽出
            pi = href.find("product_id=")
            if pi == -1:
                continue
            pid = href[pi + 11:].split("&")[0]
            if not pid or pid in seen:
                continue
            seen.add(pid)

            # タイトル（title属性 → リンクテキスト → 画像alt属性の順で取得）
            title = (anchor.get_attribute("title") or anchor.inner_text()).strip()
            title = " ".join(title.split())
            if not title or len(title) < 2:
                img_el = anchor.query_selector("img")
                if img_el:
                    alt = img_el.get_attribute("alt") or ""
                    title = " ".join(alt.split())
                if not title or len(title) < 2:
                    continue

            work_url = href if href.startswith("http") else f"https://pokedora.com{href}"

            # 親のliから声優・タグ・画像を取得
            li = anchor.query_selector("xpath=ancestor::li[1]")
            voice_actor = ""
            tags = []
            thumb_url = ""

            if li:
                # 声優
                va_links = li.query_selector_all("a")
                vas = []
                for va in va_links:
                    va_href = va.get_attribute("href") or ""
                    if "tag_type=1" in va_href:
                        vt = va.inner_text().strip()
                        if vt:
                            vas.append(vt)
                voice_actor = "、".join(vas)

                # テキスト全体からタグ抽出
                li_text = li.inner_text()
                for tc in ["NEW", "配信限定シチュエーション", "シチュエーションCD", "ドラマCD", "割引", "特典あり"]:
                    if tc in li_text:
                        tags.append(tc)

                # サムネイル（遅延読み込み対応：data-originalを優先）
                img = li.query_selector("img")
                if img:
                    src = (
                        img.get_attribute("data-original")
                        or img.get_attribute("data-src")
                        or img.get_attribute("src")
                        or ""
                    )
                    if src and "nowprinting" not in src:
                        thumb_url = src if src.startswith("http") else f"https://pokedora.com{src}"

            # フォールバック：liが見つからない、または画像が取れない場合はanchor自身のimgを使う
            if not thumb_url:
                img2 = anchor.query_selector("img")
                if img2:
                    src2 = (
                        img2.get_attribute("data-original")
                        or img2.get_attribute("data-src")
                        or img2.get_attribute("src")
                        or ""
                    )
                    if src2 and "nowprinting" not in src2:
                        thumb_url = src2 if src2.startswith("http") else f"https://pokedora.com{src2}"

            works.append({
                "rank":        len(works) + 1,
                "product_id":  pid,
                "title":       title,
                "voice_actor": voice_actor,
                "tags":        tags,
                "thumb_url":   thumb_url,
                "work_url":    work_url,
                "store":       store,
            })
            print(f"    {len(works)}位: {title[:40]}")
        except Exception as e:
            print(f"  要素取得エラー: {e}")
            continue

    print(f"  [{store}] {len(works)}件取得")
    return works


# ----------------------------------------
# JSON保存（履歴蓄積）
# ----------------------------------------

DATA_DIR = Path("docs/data")

def load_history():
    path = DATA_DIR / "history.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def save_history(history):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "history.json"
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

def save_latest(store, works):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"latest_{store}.json"
    path.write_text(json.dumps(works, ensure_ascii=False, indent=2), encoding="utf-8")

def update_history(history, store, today, works):
    if store not in history:
        history[store] = {}
    history[store][today] = {w["product_id"]: w["rank"] for w in works}
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")
    history[store] = {d: v for d, v in history[store].items() if d >= cutoff}
    return history

# ----------------------------------------
# グラフデータ生成（30日分）
# ----------------------------------------

def build_graph_data(history, store, product_ids, today):
    today_dt = datetime.strptime(today, "%Y-%m-%d")
    dates = [(today_dt - timedelta(days=29 - i)).strftime("%Y-%m-%d") for i in range(30)]
    store_history = history.get(store, {})
    graph = {}
    for pid in product_ids:
        ranks = []
        for d in dates:
            day_data = store_history.get(d, {})
            if pid in day_data:
                ranks.append(day_data[pid])
            else:
                ranks.append(None)
        graph[pid] = {"labels": dates, "ranks": ranks}
    return graph

# ----------------------------------------
# 近日配信予定（外部CSVから読み込み）
# ----------------------------------------

def load_preorders(today_str, limit=2):
    """
    data/products.csv から「販売ステータス=PREORDER」かつ発売日が今日以降の
    作品を発売日の近い順に抽出する。CSVは他の仕組みで取得・更新される想定。

    必須カラム:
      product_id, title, voice_actor, circle, release_date, stream_date,
      tags, thumb_url, work_url, status
    tags は "/" 区切りの文字列。
    """
    if not PRODUCTS_CSV.exists():
        print(f"  [preorder] {PRODUCTS_CSV} が見つからないためスキップ")
        return []

    preorders = []
    try:
        with open(PRODUCTS_CSV, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                status = (row.get("status") or "").strip().upper()
                if status != "PREORDER":
                    continue
                release_date = (row.get("release_date") or "").strip()[:10]
                if not release_date or release_date < today_str:
                    continue
                tags_raw = row.get("tags") or ""
                tags = [t.strip() for t in tags_raw.split("/") if t.strip()]
                preorders.append({
                    "product_id":   row.get("product_id", "").strip(),
                    "title":        (row.get("title") or "").strip(),
                    "voice_actor":  (row.get("voice_actor") or "").strip(),
                    "circle":       (row.get("circle") or "").strip(),
                    "release_date": release_date,
                    "stream_date":  (row.get("stream_date") or "").strip()[:10],
                    "tags":         tags[:6],
                    "thumb_url":    (row.get("thumb_url") or "").strip(),
                    "work_url":     (row.get("work_url") or "").strip(),
                })
    except Exception as e:
        print(f"  [preorder] CSV読み込みエラー: {e}")
        return []

    preorders.sort(key=lambda x: x["release_date"])
    print(f"  [preorder] 近日配信予定: {len(preorders)}件 中 上位{limit}件を表示")
    return preorders[:limit]

# ----------------------------------------
# 静的HTML生成
# ----------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ポケドラ ランキング分析</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@400;500&family=Noto+Sans+JP:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
    --rose-50:#fff1f4;--rose-100:#fde0e7;--rose-600:#d4386f;
    --rose-800:#8b1a42;--mauve-50:#fdf4f8;
    --text-main:#3a1628;--text-sub:#8b4f6a;--text-muted:#b8829a;
    --border:#f0c4d8;--border-light:#fae0ec;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Noto Sans JP',sans-serif;background:var(--rose-50);color:var(--text-main);min-height:100vh}
.site-wrap{max-width:1200px;margin:0 auto;padding:20px 16px 60px}
.header{display:flex;align-items:center;gap:14px;padding:16px 24px;background:#fff;border:0.5px solid var(--border);border-radius:16px;margin-bottom:20px}
.header-icon{width:38px;height:38px;border-radius:50%;background:var(--rose-100);display:flex;align-items:center;justify-content:center;font-size:18px}
.header-title{font-family:'Noto Serif JP',serif;font-size:18px;font-weight:500;color:var(--rose-800);letter-spacing:.04em}
.header-sub{font-size:12px;font-weight:500;color:var(--rose-600);margin-top:3px;letter-spacing:.02em;border-left:2.5px solid var(--rose-600);padding-left:7px}
.header-update{margin-left:auto;font-size:11px;color:var(--rose-600);background:var(--rose-50);border:0.5px solid var(--border);border-radius:20px;padding:5px 12px;white-space:nowrap}
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px}
.stat-card{background:#fff;border:0.5px solid var(--border);border-radius:14px;padding:14px 16px}
.stat-label{font-size:11px;color:var(--text-muted);margin-bottom:6px}
.stat-value{font-family:'Noto Serif JP',serif;font-size:26px;font-weight:500;color:var(--rose-800)}
.stat-sub{font-size:10px;color:var(--text-muted);margin-top:3px}
.section{margin-bottom:28px}
.section-head{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.section-title{font-family:'Noto Serif JP',serif;font-size:15px;font-weight:500;color:var(--rose-800)}
.section-badge{font-size:10px;background:var(--rose-100);color:var(--rose-600);border:0.5px solid var(--border);border-radius:20px;padding:2px 9px}
.section-badge-new{font-size:10px;background:#ecfdf5;color:#065f46;border:0.5px solid #6ee7b7;border-radius:20px;padding:2px 9px}
.table-card{background:#fff;border:0.5px solid var(--border);border-radius:16px;overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}
thead th{background:var(--mauve-50);color:var(--rose-800);font-weight:500;padding:10px 8px;border-bottom:0.5px solid var(--border-light);text-align:left;font-size:11px}
tbody td{padding:6px 8px;border-bottom:0.5px solid var(--border-light);vertical-align:top}
tbody td.thumb-wrap{vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--rose-50)}
.rb{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;font-size:11px;font-weight:500}
.r1{background:#fef3c7;color:#92400e;border:0.5px solid #fde68a}
.r2{background:#f1f5f9;color:#475569;border:0.5px solid #e2e8f0}
.r3{background:#fef0e6;color:#9a3412;border:0.5px solid #fed7aa}
.rn{background:var(--rose-50);color:var(--text-muted);border:0.5px solid var(--border-light)}
.thumb-wrap{width:150px;min-width:150px;padding:4px 6px 4px 8px;position:relative}
.thumb-wrap img{width:146px;height:110px;object-fit:cover;border-radius:8px;border:0.5px solid var(--border-light);display:block}
.thumb-wrap a{display:block}
.thumb-rank{position:absolute;top:7px;left:11px;z-index:1}
.title-cell{padding-left:8px !important}
.work-title{font-weight:500;color:var(--rose-800);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.work-title a{color:var(--rose-800);text-decoration:none}
.work-title a:hover{color:var(--rose-600);text-decoration:underline}
.work-circle{font-size:10px;color:var(--text-muted);margin-top:2px}
.work-date{display:inline-block;margin-right:6px;color:var(--rose-600)}
.release-date-cell{font-size:12px;color:var(--rose-800);font-weight:500}
.bonus-badge{font-size:10px;background:#ecfdf5;color:#065f46;border:0.5px solid #6ee7b7;border-radius:20px;padding:2px 9px;margin-left:6px}
.genres{display:flex;flex-wrap:wrap;gap:3px;margin-top:3px}
.gtag{display:inline-block;font-size:9px;background:var(--rose-50);color:var(--text-muted);border:0.5px solid var(--border-light);border-radius:20px;padding:1px 6px;white-space:nowrap}
.rise-pill{display:inline-flex;align-items:center;gap:2px;background:var(--rose-50);color:var(--rose-600);border:0.5px solid var(--border);border-radius:20px;padding:3px 8px;font-size:11px;font-weight:500}
.tup{font-size:11px;font-weight:500;color:#be123c}
.tdn{font-size:11px;font-weight:500;color:#0369a1}
.tsm{font-size:11px;color:var(--text-muted)}
.tnew{display:inline-flex;align-items:center;gap:2px;background:#ecfdf5;color:#065f46;border:0.5px solid #6ee7b7;border-radius:20px;padding:2px 7px;font-size:10px;font-weight:500}
.chart-cell{width:240px}
.chart-wrap{width:100%;height:80px;cursor:pointer}
.no-data{font-size:11px;color:var(--text-muted)}
.empty-msg{text-align:center;padding:20px;color:var(--text-muted);font-size:12px}
.footer{text-align:center;margin-top:40px;font-size:11px;color:var(--text-muted);padding-top:20px;border-top:0.5px solid var(--border-light)}
@media (max-width:640px){
    .site-wrap{padding:10px 8px 40px}
    .header{padding:10px 12px;gap:8px;flex-wrap:wrap}
    .header-title{font-size:13px}
    .header-sub{font-size:10px}
    .header-update{font-size:9px;padding:3px 8px;margin-left:0;width:100%}
    .stat-row{grid-template-columns:repeat(3,1fr);gap:5px}
    .stat-card{padding:8px 6px}
    .stat-value{font-size:18px}
    .stat-label{font-size:8px}
    .stat-sub{font-size:7px}
    .table-card{overflow:visible}
    table{display:block}
    thead{display:none}
    tbody{display:flex;flex-direction:column;gap:6px;padding:6px}
    tbody tr{display:grid;grid-template-columns:110px 1fr;grid-template-rows:auto auto auto;background:#fff;border:0.5px solid var(--border);border-radius:10px;overflow:hidden;padding:0}
    tbody td{border-bottom:none;padding:0;width:auto !important}
    tbody tr:hover td{background:transparent}
    .thumb-wrap{grid-column:1;grid-row:1/4;width:110px !important;min-width:110px;padding:6px 4px 6px 6px;position:relative}
    .thumb-wrap img{width:100px;height:75px;border-radius:6px;border:0.5px solid var(--border-light);display:block;object-fit:cover}
    .thumb-rank{top:9px;left:9px}
    .title-cell{grid-column:2;grid-row:1;padding:6px 8px 2px 4px !important;display:block}
    .work-title{font-size:11px;white-space:normal;line-height:1.3}
    .work-circle{font-size:9px;margin-top:1px}
    .genres{margin-top:3px;gap:2px}
    .gtag{font-size:8px;padding:1px 4px}
    .chart-cell{grid-column:1/3;grid-row:4;width:100% !important}
    .chart-wrap{height:72px;padding:0 4px 6px;display:block}
    .section-title{font-size:13px}
    .section-badge,.section-badge-new{font-size:9px}
    .section{margin-bottom:20px}
    .section-head{margin-bottom:6px}
}
</style>
</head>
<body>
<div class="site-wrap">

<div class="header">
    <div class="header-icon">🎧</div>
    <div>
        <div class="header-title">ポケドラ ランキング分析</div>
        <div class="header-sub">ドラマCD人気作品データ</div>
    </div>
    <div class="header-update">🔄 毎日23:30頃更新 ／ @@TODAY_STR@@</div>
</div>

<div class="stat-row">
    <div class="stat-card">
        <div class="stat-label">📦 収録作品数</div>
        <div class="stat-value">@@TOTAL_WORKS@@</div>
        <div class="stat-sub">オトナ向けランキング</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">✨ 新着</div>
        <div class="stat-value">@@NEW_TODAY@@</div>
        <div class="stat-sub">@@TODAY_STR@@</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">📈 急上昇作品</div>
        <div class="stat-value">@@RISING_COUNT@@</div>
        <div class="stat-sub">前日比10位以上上昇</div>
    </div>
</div>

@@PREORDER_SECTION@@

@@RISING_SECTION@@

<div class="section">
    <div class="section-head">
        <span style="font-size:16px">🏆</span>
        <span class="section-title">本日のランキング</span>
        <span class="section-badge">TOP 10</span>
    </div>
    <div class="table-card">
    <table>
        <colgroup>
            <col style="width:150px">
            <col style="width:auto">
            <col style="width:10%">
            <col style="width:7%">
            <col style="width:28%">
        </colgroup>
        <thead>
            <tr><th></th><th>タイトル / 声優</th><th>声優</th><th>推移</th><th class="chart-cell">推移グラフ（30日）</th></tr>
        </thead>
        <tbody>
@@RANKING_ROWS@@
        </tbody>
    </table>
    </div>
</div>

<div class="footer">
    ポケドラ ランキング分析 ／ データは毎日23:30頃に自動更新されます<br>
    ※ 本サイトはポケットドラマCD（ポケドラ）のデータを使用しています
</div>

</div>
<script>
const graphData = @@GRAPH_DATA_JSON@@;
const PINK = '#e8528a';

function drawChart(canvasId, pid) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    const d = graphData[pid];
    if (!d) { ctx.parentElement.innerHTML = '<span class="no-data">データ蓄積中</span>'; return; }
    const disp = d.ranks.map(v => (v === null || v === undefined) ? null : (v > 14 ? 15 : v));
    const isSingle = d.ranks.filter(v => v !== null).length === 1;
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: d.labels,
            datasets: [{
                data: disp,
                borderColor: PINK,
                backgroundColor: 'transparent',
                borderWidth: 1.5,
                pointRadius: isSingle ? 5 : 2,
                pointHoverRadius: 6,
                pointBackgroundColor: PINK,
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
                        font: { size: 11 }, color: '#b8829a',
                        callback: v => v===1?'1位':v===5?'5位':v===10?'10位':v===15?'圏外':null
                    },
                    beforeFit: axis => {
                        axis.ticks = [{value:1,label:'1位'},{value:5,label:'5位'},{value:10,label:'10位'},{value:15,label:'圏外'}];
                    },
                    grid: { color: 'rgba(232,82,138,0.07)' },
                    border: { display: false }
                },
                x: {
                    ticks: { font: { size: 9 }, color: '#b8829a', maxTicksLimit: 4 },
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
                    backgroundColor: 'rgba(139,26,66,0.85)',
                    titleColor: '#fde0e7', bodyColor: '#fff',
                }
            }
        }
    });
}

document.querySelectorAll('canvas[data-pid]').forEach(c => drawChart(c.id, c.dataset.pid));
</script>
</body>
</html>
"""

def rank_badge(rank):
    cls = {1: "r1", 2: "r2", 3: "r3"}.get(rank, "rn")
    return f'<span class="rb {cls}">{rank}</span>'

def thumb_html(w):
    if w.get("thumb_url"):
        return f'<img src="{w["thumb_url"]}" alt="" loading="lazy">'
    return '<div style="width:146px;height:110px;border-radius:8px;background:var(--rose-100);display:flex;align-items:center;justify-content:center;font-size:28px">🎧</div>'

def tags_html(tags):
    if not tags:
        return ""
    parts = [f'<span class="gtag">{t}</span>' for t in tags]
    return f'<div class="genres">{"".join(parts)}</div>'

def change_html(rank_change, is_new):
    if is_new:
        return '<span class="tnew">🆕 新着</span>'
    if rank_change > 0:
        return f'<span class="tup">▲{rank_change}</span>'
    if rank_change < 0:
        return f'<span class="tdn">▼{abs(rank_change)}</span>'
    return '<span class="tsm">－</span>'

def make_row(w, rank_change, is_new, canvas_id):
    rb = rank_badge(w["rank"])
    th = thumb_html(w)
    tg = tags_html(w.get("tags", []))
    ch = change_html(rank_change, is_new)
    return f"""        <tr>
            <td class="thumb-wrap">
                <span class="thumb-rank">{rb}</span>
                <a href="{w['work_url']}" target="_blank" rel="noopener">{th}</a>
            </td>
            <td class="title-cell">
                <div class="work-title"><a href="{w['work_url']}" target="_blank" rel="noopener">{w['title']}</a></div>
                <div class="work-circle">{w.get('voice_actor','')}</div>
                {tg}
            </td>
            <td style="font-size:11px;color:var(--text-sub)">{w.get('voice_actor','')}</td>
            <td>{ch}</td>
            <td class="chart-cell"><canvas id="{canvas_id}" class="chart-wrap" data-pid="{w['product_id']}"></canvas></td>
        </tr>"""

def make_rising_row(w, rise, canvas_id):
    rb = rank_badge(w["rank"])
    th = thumb_html(w)
    tg = tags_html(w.get("tags", []))
    return f"""        <tr>
            <td class="thumb-wrap">
                <span class="thumb-rank">{rb}</span>
                <a href="{w['work_url']}" target="_blank" rel="noopener">{th}</a>
            </td>
            <td class="title-cell">
                <div class="work-title"><a href="{w['work_url']}" target="_blank" rel="noopener">{w['title']}</a></div>
                <div class="work-circle">{w.get('voice_actor','')}</div>
                {tg}
            </td>
            <td style="font-size:11px;color:var(--text-sub)">{w.get('voice_actor','')}</td>
            <td><span class="rise-pill">▲{rise}位UP</span></td>
            <td class="chart-cell"><canvas id="{canvas_id}" class="chart-wrap" data-pid="{w['product_id']}"></canvas></td>
        </tr>"""

def make_preorder_row(p, index):
    rb = rank_badge(index + 1)
    if p.get("thumb_url"):
        th = f'<img src="{p["thumb_url"]}" alt="" loading="lazy">'
    else:
        th = '<div style="width:146px;height:110px;border-radius:8px;background:var(--rose-100);display:flex;align-items:center;justify-content:center;font-size:28px">🎧</div>'
    tg = tags_html(p.get("tags", []))
    work_url = p.get("work_url") or "#"
    stream_date_html = (
        f'<span class="work-date">配信開始: {p["stream_date"]}</span>'
        if p.get("stream_date") else ""
    )
    return f"""        <tr>
            <td class="thumb-wrap">
                <span class="thumb-rank">{rb}</span>
                <a href="{work_url}" target="_blank" rel="noopener">{th}</a>
            </td>
            <td class="title-cell">
                <div class="work-title"><a href="{work_url}" target="_blank" rel="noopener">{p['title']}</a></div>
                <div class="work-circle">{stream_date_html}{p.get('circle','')}</div>
                {tg}
            </td>
            <td style="font-size:11px;color:var(--text-sub)">{p.get('voice_actor','')}</td>
            <td class="release-date-cell">{p.get('release_date','')}</td>
        </tr>"""

def generate_html(ranking, rising, preorders, graph_data, today_str, total_works, new_today):
    top10 = ranking[:10]
    today_dt = datetime.strptime(today_str.replace("/", "-"), "%Y-%m-%d")
    prev_date = (today_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_map = {}
    for pid, gd in graph_data.items():
        if prev_date in gd["labels"]:
            idx = gd["labels"].index(prev_date)
            v = gd["ranks"][idx]
            if v and v <= 30:
                prev_map[pid] = v

    ranking_rows = []
    for i, w in enumerate(top10):
        pid = w["product_id"]
        prev = prev_map.get(pid, 0)
        rank_change = (prev - w["rank"]) if prev else 0
        is_new = (pid not in prev_map)
        ranking_rows.append(make_row(w, rank_change, is_new, f"wc_{i+1}"))

    if rising:
        rows = []
        for i, (w, rise) in enumerate(rising):
            rows.append(make_rising_row(w, rise, f"rc_{i+1}"))
        rising_section = f"""<div class="section">
    <div class="section-head">
        <span style="font-size:16px">🔥</span>
        <span class="section-title">急上昇作品</span>
        <span class="section-badge">前日比10位以上上昇</span>
    </div>
    <div class="table-card">
    <table>
        <colgroup>
            <col style="width:150px"><col style="width:auto">
            <col style="width:10%"><col style="width:8%"><col style="width:28%">
        </colgroup>
        <thead>
            <tr><th></th><th>タイトル / 声優</th><th>声優</th><th>上昇幅</th><th class="chart-cell">推移グラフ（30日）</th></tr>
        </thead>
        <tbody>
{"".join(rows)}
        </tbody>
    </table>
    </div>
</div>"""
    else:
        rising_section = ""

    if preorders:
        prows = [make_preorder_row(p, i) for i, p in enumerate(preorders)]
        preorder_section = f"""<div class="section">
    <div class="section-head">
        <span style="font-size:16px">🔔</span>
        <span class="section-title">近日配信予定</span>
        <span class="section-badge">データあり・配信開始前</span>
    </div>
    <div class="table-card">
    <table>
        <colgroup>
            <col style="width:150px"><col style="width:auto">
            <col style="width:10%"><col style="width:12%">
        </colgroup>
        <thead>
            <tr><th></th><th>タイトル / 声優</th><th>声優</th><th>発売予定日</th></tr>
        </thead>
        <tbody>
{"".join(prows)}
        </tbody>
    </table>
    </div>
</div>"""
    else:
        preorder_section = ""

    html = HTML_TEMPLATE
    html = html.replace("@@TODAY_STR@@", today_str)
    html = html.replace("@@TOTAL_WORKS@@", str(total_works))
    html = html.replace("@@NEW_TODAY@@", str(new_today))
    html = html.replace("@@RISING_COUNT@@", str(len(rising)))
    html = html.replace("@@PREORDER_SECTION@@", preorder_section)
    html = html.replace("@@RISING_SECTION@@", rising_section)
    html = html.replace("@@RANKING_ROWS@@", "\n".join(ranking_rows))
    html = html.replace("@@GRAPH_DATA_JSON@@", json.dumps(graph_data, ensure_ascii=False))
    return html

# ----------------------------------------
# メイン
# ----------------------------------------

def run():
    today = now_jst().strftime("%Y-%m-%d")
    today_str = now_jst().strftime("%Y/%m/%d")
    print(f"\n=== ポケドラ スクレイピング開始: {today} ===")

    history = load_history()

    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ])
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))
        context.add_cookies([{
            "name": "age_check",
            "value": "1",
            "domain": "pokedora.com",
            "path": "/",
        }])
        page = context.new_page()

        store = "adt"
        label, url = CATEGORIES[store]
        print(f"\n--- {label} ---")
        works = fetch_ranking(page, store, url)
        browser.close()

    if not works:
        print("取得データなし・終了")
        return

    save_latest(store, works)
    history = update_history(history, store, today, works)
    save_history(history)

    prev_date = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_data = history.get(store, {}).get(prev_date, {})

    rising = []
    for w in works:
        pid = w["product_id"]
        prev_rank = prev_data.get(pid)
        if prev_rank and (prev_rank - w["rank"]) >= 10:
            rising.append((w, prev_rank - w["rank"]))
    rising.sort(key=lambda x: -x[1])
    rising = rising[:5]

    all_pids = list(dict.fromkeys(
        [w["product_id"] for w in works[:10]] +
        [w["product_id"] for w, _ in rising]
    ))
    graph_data = build_graph_data(history, store, all_pids, today)

    total_works = len(works)
    new_today = sum(1 for w in works if w["product_id"] not in prev_data)

    preorders = load_preorders(today)

    html = generate_html(works, rising, preorders, graph_data, today_str, total_works, new_today)

    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"\n✅ docs/index.html 生成完了")

if __name__ == "__main__":
    run()
