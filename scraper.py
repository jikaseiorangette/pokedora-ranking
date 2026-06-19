# scraper.py
# ポケドラのランキングをスクレイプし、JSONと静的HTMLを生成する

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

def now_jst():
    return datetime.now(JST)

CATEGORIES = {
    "adt":    ("オトナ向け", "https://pokedora.com/ranking/index.php?store=adt&term=1&age_check=1"),
    "adt-bl": ("オトナBL",   "https://pokedora.com/ranking/index.php?store=adt-bl&term=1&age_check=1"),
    "home":   ("一般",       "https://pokedora.com/ranking/index.php?store=home&term=1"),
    "bl":     ("BL",         "https://pokedora.com/ranking/index.php?store=bl&term=1"),
}

# ----------------------------------------
# スクレイピング
# ----------------------------------------

def fetch_ranking(page, store, url):
    print(f"  [{store}] アクセス中: {url}")
    for attempt in range(3):
        try:
            # networkidleは常時通信があるサイトでタイムアウトしやすいため
            # domcontentloadedに変更し、タイムアウトも延長
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            break
        except Exception as e:
            print(f"  失敗({attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(10)
            else:
                raise
    # ページ内のJS描画・年齢確認リダイレクトなどを待つため少し長めに待機
    time.sleep(6)

    # ===== 年齢確認ページの自動突破を試みる =====
    try:
        for label in ["はい", "はい、18歳以上です", "ENTER", "Yes", "18歳以上"]:
            btn = page.locator(f"a:has-text('{label}'), button:has-text('{label}')").first
            if btn.count() > 0:
                print(f"  [DEBUG] 年齢確認ボタン「{label}」をクリックします")
                btn.click(timeout=5000)
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                time.sleep(3)
                break
    except Exception as e:
        print(f"  [DEBUG] 年齢確認ボタン処理でエラー（無視して続行): {e}")

    # ===== デバッグ情報出力 =====
    print(f"  [DEBUG] 現在のURL: {page.url}")
    print(f"  [DEBUG] ページタイトル: {page.title()}")

    soup = BeautifulSoup(page.content(), "html.parser")

    # 年齢確認ページに留まっていないか簡易チェック
    page_text = soup.get_text()
    if "18歳未満" in page_text or "年齢確認" in page_text:
        print("  [DEBUG] ⚠️ 年齢確認ページに留まっている可能性があります")
        for el in soup.select("a, button"):
            t = el.get_text(strip=True)
            if t in ("はい", "はい、18歳以上です", "ENTER", "Yes", "18歳以上"):
                print(f"  [DEBUG] 年齢確認ボタン候補発見: <{el.name}> text='{t}' href='{el.get('href','')}'")

    n_product_id_links = len(soup.select("a[href*='product_id']"))
    n_detail_links = len(soup.select("a[href*='/products/detail.php']"))
    print(f"  [DEBUG] product_id を含むリンク数: {n_product_id_links}")
    print(f"  [DEBUG] /products/detail.php を含むリンク数: {n_detail_links}")
    print(f"  [DEBUG] HTML先頭500文字: {str(soup)[:500]}")

    works = []
    seen = set()

    # product_thumb_imageクラスのimgタグから作品情報を抽出
    for img in soup.select("img.product_thumb_image"):
        if len(works) >= 30:
            break

        # タイトルはalt属性
        title = img.get("alt", "").strip()
        title = re.sub(r'\s+', ' ', title)
        if not title or len(title) < 2:
            continue

        # 親要素からproduct_idを含むリンクを探す
        parent = img.find_parent()
        pid = None
        work_url = ""
        for _ in range(6):  # 最大6階層上まで探す
            if parent is None:
                break
            link = parent.find("a", href=re.compile(r'product_id=\d+'))
            if link:
                m = re.search(r'product_id=(\d+)', link.get("href", ""))
                if m:
                    pid = m.group(1)
                    href = link.get("href", "")
                    work_url = href if href.startswith("http") else f"https://pokedora.com{href}"
                break
            parent = parent.find_parent()

        if not pid or pid in seen:
            continue
        seen.add(pid)

        # サムネイルURL
        src = img.get("src", "")
        thumb_url = ""
        if src and "nowprinting" not in src:
            thumb_url = src if src.startswith("http") else f"https://pokedora.com{src}"

        # 声優・タグは同一li/div内から取得
        container = img.find_parent("li") or img.find_parent("div")
        voice_actor = ""
        tags = []
        if container:
            vas = [a.get_text(strip=True) for a in container.select("a[href*='tag_type=1']") if a.get_text(strip=True)]
            voice_actor = "、".join(vas)
            ct = container.get_text()
            for tc in ["NEW", "配信限定シチュエーション", "シチュエーションCD", "ドラマCD", "割引", "特典あり"]:
                if tc in ct:
                    tags.append(tc)

        works.append({
            "rank":        len(works) + 1,
            "product_id":  pid,
            "title":       title,
            "voice_actor": voice_actor,
            "tags":        tags,
            "thumb_url":   thumb_url,
            "work_url":    work_url or f"https://pokedora.com/products/detail.php?product_id={pid}",
        })
        print(f"    {len(works)}位: {title[:40]}")

    print(f"  [{store}] {len(works)}件取得")
    return works

# ----------------------------------------
# JSON保存（履歴蓄積）
# ----------------------------------------

DATA_DIR = Path("data")

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
    """historyにその日のランキングを記録（product_id: rank の辞書形式）"""
    if store not in history:
        history[store] = {}
    history[store][today] = {w["product_id"]: w["rank"] for w in works}
    # 90日以上前のデータを削除
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
.genres{display:flex;flex-wrap:wrap;gap:3px;margin-top:3px}
.gtag{display:inline-block;font-size:9px;background:var(--rose-50);color:var(--text-muted);border:0.5px solid var(--border-light);border-radius:20px;padding:1px 6px;white-space:nowrap}
.rise-pill{display:inline-flex;align-items:center;gap:2px;background:var(--rose-50);color:var(--rose-600);border:0.5px solid var(--border);border-radius:20px;padding:3px 8px;font-size:11px;font-weight:500}
.new-pill{display:inline-flex;align-items:center;gap:2px;background:#ecfdf5;color:#065f46;border:0.5px solid #6ee7b7;border-radius:20px;padding:3px 8px;font-size:11px;font-weight:500}
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
    <div class="header-update">🔄 毎日23:30頃更新 ／ {today_str}</div>
</div>

<div class="stat-row">
    <div class="stat-card">
        <div class="stat-label">📦 収録作品数</div>
        <div class="stat-value">{total_works}</div>
        <div class="stat-sub">オトナ向けランキング</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">✨ 新着</div>
        <div class="stat-value">{new_today}</div>
        <div class="stat-sub">{today_str}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">🔔 近日配信予定</div>
        <div class="stat-value">{rising_count}</div>
        <div class="stat-sub">配信開始前の作品</div>
    </div>
</div>

{rising_section}

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
{ranking_rows}
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
const graphData = {graph_data_json};
const PINK = '#e8528a';

function drawChart(canvasId, pid) {{
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    const d = graphData[pid];
    if (!d) {{ ctx.parentElement.innerHTML = '<span class="no-data">データ蓄積中</span>'; return; }}
    const disp = d.ranks.map(v => (v === null || v === undefined) ? null : (v > 14 ? 15 : v));
    const isSingle = d.ranks.filter(v => v !== null).length === 1;
    new Chart(ctx, {{
        type: 'line',
        data: {{
            labels: d.labels,
            datasets: [{{
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
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            layout: {{ padding: {{ top: 6, left: 2 }} }},
            interaction: {{ mode: 'index', intersect: false }},
            scales: {{
                y: {{
                    reverse: true, min: -1, max: 17,
                    ticks: {{
                        font: {{ size: 11 }}, color: '#b8829a',
                        callback: v => v===1?'1位':v===5?'5位':v===10?'10位':v===15?'圏外':null
                    }},
                    beforeFit: axis => {{
                        axis.ticks = [{{value:1,label:'1位'}},{{value:5,label:'5位'}},{{value:10,label:'10位'}},{{value:15,label:'圏外'}}];
                    }},
                    grid: {{ color: 'rgba(232,82,138,0.07)' }},
                    border: {{ display: false }}
                }},
                x: {{
                    ticks: {{ font: {{ size: 9 }}, color: '#b8829a', maxTicksLimit: 4 }},
                    grid: {{ display: false }}, border: {{ display: false }}
                }}
            }},
            plugins: {{
                legend: {{ display: false }},
                tooltip: {{
                    callbacks: {{
                        label: c => {{
                            const raw = d.ranks[c.dataIndex];
                            if (raw === null || raw === undefined) return '';
                            return raw > 30 ? '圏外' : raw + '位';
                        }}
                    }},
                    titleFont: {{ size: 11 }}, bodyFont: {{ size: 12 }}, padding: 8,
                    backgroundColor: 'rgba(139,26,66,0.85)',
                    titleColor: '#fde0e7', bodyColor: '#fff',
                }}
            }}
        }}
    }});
}}

document.querySelectorAll('canvas[data-pid]').forEach(c => drawChart(c.id, c.dataset.pid));
</script>
</body>
</html>
"""

def rank_badge(rank):
    cls = {1: "r1", 2: "r2", 3: "r3"}.get(rank, "rn")
    return f'<span class="rb {cls}">{rank}</span>'

def thumb_html(w):
    if w["thumb_url"]:
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
    tg = tags_html(w["tags"])
    ch = change_html(rank_change, is_new)
    return f"""        <tr>
            <td class="thumb-wrap">
                <span class="thumb-rank">{rb}</span>
                <a href="{w['work_url']}" target="_blank" rel="noopener">{th}</a>
            </td>
            <td class="title-cell">
                <div class="work-title"><a href="{w['work_url']}" target="_blank" rel="noopener">{w['title']}</a></div>
                <div class="work-circle">{w['voice_actor']}</div>
                {tg}
            </td>
            <td style="font-size:11px;color:var(--text-sub)">{w['voice_actor']}</td>
            <td>{ch}</td>
            <td class="chart-cell"><canvas id="{canvas_id}" class="chart-wrap" data-pid="{w['product_id']}"></canvas></td>
        </tr>"""

def make_rising_row(w, rise, canvas_id):
    rb = rank_badge(w["rank"])
    th = thumb_html(w)
    tg = tags_html(w["tags"])
    return f"""        <tr>
            <td class="thumb-wrap">
                <span class="thumb-rank">{rb}</span>
                <a href="{w['work_url']}" target="_blank" rel="noopener">{th}</a>
            </td>
            <td class="title-cell">
                <div class="work-title"><a href="{w['work_url']}" target="_blank" rel="noopener">{w['title']}</a></div>
                <div class="work-circle">{w['voice_actor']}</div>
                {tg}
            </td>
            <td style="font-size:11px;color:var(--text-sub)">{w['voice_actor']}</td>
            <td><span class="rise-pill">▲{rise}位UP</span></td>
            <td class="chart-cell"><canvas id="{canvas_id}" class="chart-wrap" data-pid="{w['product_id']}"></canvas></td>
        </tr>"""

def extract_preorders(works):
    """タイトルに配信開始日が含まれる作品を近日配信予定として抽出（発売日順）"""
    preorders = []
    for w in works:
        m = re.search(r'《?配信開始は(\d{4}年\d{1,2}月\d{1,2}日)', w["title"])
        if m:
            date_str = m.group(1)
            # YYYY年MM月DD日 → YYYY-MM-DD
            dm = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_str)
            if dm:
                release_date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
                # タイトルから《配信開始は...》を除去
                clean_title = re.sub(r'《?配信開始は[^》）]+[》）]?\s*', '', w["title"]).strip()
                preorders.append({**w, "release_date": release_date, "clean_title": clean_title})
    preorders.sort(key=lambda x: x["release_date"])
    return preorders[:5]


def make_preorder_row(w, index):
    pid = w["product_id"]
    title = w.get("clean_title", w["title"])
    release_date = w.get("release_date", "")
    url = w["work_url"]
    img = w["thumb_url"]
    voice = w.get("voice_actor", "")
    tags = w.get("tags", [])
    rb_cls = "rn"
    rb = f'<span class="rb {rb_cls}">{index+1}</span>'
    tag_html = "".join(f'<span class="gtag">{t}</span>' for t in tags[:4])
    return f"""<tr>
            <td class="thumb-wrap">
                <span class="thumb-rank">{rb}</span>
                <a href="{url}" target="_blank" rel="noopener"><img src="{img}" alt="" loading="lazy"></a>
            </td>
            <td class="title-cell">
                <div class="work-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
                <div class="work-circle">{voice}</div>
                <div class="genres">{tag_html}</div>
            </td>
            <td style="font-size:11px;color:var(--text-sub)">{voice}</td>
            <td class="release-date-cell">{release_date}</td>
        </tr>"""


def generate_html(ranking, preorders, graph_data, today_str, total_works, new_today):
    # TOP10のみ表示
    top10 = ranking[:10]

    # 前日ランク取得用マップ
    prev_map = {}
    today_dt = datetime.strptime(today_str.replace("/", "-"), "%Y-%m-%d")
    prev_date = (today_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    for pid, gd in graph_data.items():
        if prev_date in gd["labels"]:
            idx = gd["labels"].index(prev_date)
            v = gd["ranks"][idx]
            if v and v <= 30:
                prev_map[pid] = v

    # ランキング行
    ranking_rows = []
    for i, w in enumerate(top10):
        pid = w["product_id"]
        prev = prev_map.get(pid, 0)
        rank_change = (prev - w["rank"]) if prev else 0
        is_new = (pid not in prev_map)
        ranking_rows.append(make_row(w, rank_change, is_new, f"wc_{i+1}"))

    # 近日配信予定セクション
    if preorders:
        rows = [make_preorder_row(w, i) for i, w in enumerate(preorders)]
        preorder_section = f"""<div class="section">
    <div class="section-head">
        <span style="font-size:16px">🔔</span>
        <span class="section-title">近日配信予定</span>
        <span class="section-badge">配信開始前の作品</span>
    </div>
    <div class="table-card">
    <table>
        <colgroup>
            <col style="width:150px"><col style="width:auto">
            <col style="width:10%"><col style="width:12%">
        </colgroup>
        <thead>
            <tr><th></th><th>タイトル / 声優</th><th>声優</th><th>配信予定日</th></tr>
        </thead>
        <tbody>
{"".join(rows)}
        </tbody>
    </table>
    </div>
</div>"""
    else:
        preorder_section = ""

    html = HTML_TEMPLATE.format(
        today_str=today_str,
        total_works=total_works,
        new_today=new_today,
        rising_count=len(preorders),
        rising_section=preorder_section,
        ranking_rows="\n".join(ranking_rows),
        graph_data_json=json.dumps(graph_data, ensure_ascii=False),
    )
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
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))

        # オトナ向けのみメインページとして生成（がるまに方式に合わせる）
        store = "adt"
        label, url = CATEGORIES[store]
        print(f"\n--- {label} ---")

        works = fetch_ranking(page, store, url)
        browser.close()

    if not works:
        print("取得データなし・終了")
        return

    # JSON保存
    save_latest(store, works)
    history = update_history(history, store, today, works)
    save_history(history)

    # 前日データ
    prev_date = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_data = history.get(store, {}).get(prev_date, {})

    # 近日配信予定（タイトルに配信開始日を含む作品）
    preorders = extract_preorders(works)

    # グラフデータ（TOP10 + 近日配信予定）
    all_pids = list(dict.fromkeys(
        [w["product_id"] for w in works[:10]] +
        [w["product_id"] for w in preorders]
    ))
    graph_data = build_graph_data(history, store, all_pids, today)

    # ranking-hub用：graph_dataを単体JSONとして保存
    graph_path = DATA_DIR / f"graph_{store}.json"
    graph_path.write_text(json.dumps(graph_data, ensure_ascii=False), encoding="utf-8")
    print(f"  graph_{store}.json 保存完了（{len(graph_data)}件）")

    # 統計
    total_works = len(works)
    new_today = sum(1 for w in works if w["product_id"] not in prev_data)

    # ranking-hub用：統計情報を単体JSONとして保存
    meta = {
        "updated": today_str,
        "total_works": total_works,
        "new_today": new_today,
        "preorder_count": len(preorders),
        "preorders": [
            {
                "id": w["product_id"],
                "title": w.get("clean_title", w["title"]),
                "voice_actor": w.get("voice_actor", ""),
                "release_date": w.get("release_date", ""),
                "thumb_url": w["thumb_url"],
                "work_url": w["work_url"],
                "tags": w.get("tags", [])[:4],
            }
            for w in preorders
        ],
    }
    meta_path = DATA_DIR / f"meta_{store}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print(f"  meta_{store}.json 保存完了（近日配信予定: {len(preorders)}件）")

    # HTML生成
    html = generate_html(works, preorders, graph_data, today_str, total_works, new_today)

    # docs/index.html に出力（GitHub Pages用）
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"\n✅ docs/index.html 生成完了")

if __name__ == "__main__":
    run()
