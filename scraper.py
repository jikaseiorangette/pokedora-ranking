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
    # JS描画完了まで待機（ランキングリストはJS描画のため長めに）
    time.sleep(10)

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
    n_thumb_imgs = len(soup.select("img.product_thumb_image"))
    print(f"  [DEBUG] product_id を含むリンク数: {n_product_id_links}")
    print(f"  [DEBUG] img.product_thumb_image の件数: {n_thumb_imgs}")

    works = []
    seen = set()

    # 元の実績あるセレクタに戻す：a[href*='/products/detail.php']
    # タイトルはリンク内imgのalt属性から取得（以前はget_text()で空になっていた）
    for link in soup.select("a[href*='/products/detail.php']"):
        if len(works) >= 30:
            break
        href = link.get("href", "")
        m = re.search(r'product_id=(\d+)', href)
        if not m:
            continue
        pid = m.group(1)
        if pid in seen:
            continue

        # タイトル：リンク内imgのalt属性を優先
        img_el = link.find("img")
        if img_el and img_el.get("alt", "").strip():
            title = img_el.get("alt", "").strip()
        else:
            title = link.get_text(separator=" ").strip()
        title = re.sub(r'\s+', ' ', title)
        if not title or len(title) < 2:
            continue

        seen.add(pid)
        work_url = href if href.startswith("http") else f"https://pokedora.com{href}"

        # サムネイル
        thumb_url = ""
        if img_el:
            src = img_el.get("src", "")
            if src and "nowprinting" not in src:
                thumb_url = src if src.startswith("http") else f"https://pokedora.com{src}"

        # 声優・タグは親のli/divから
        container = link.find_parent("li") or link.find_parent("div")
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
            "work_url":    work_url,
        })
        print(f"    {len(works)}位: {title[:40]}")

    print(f"  [{store}] {len(works)}件取得")
    return works

# ----------------------------------------
# JSON保存（履歴蓄積）
# ----------------------------------------

DATA_DIR = Path("data")

def load_work_meta():
    """作品メタデータ（発売日など）を読み込む"""
    path = DATA_DIR / "work_meta.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def save_work_meta(work_meta):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "work_meta.json"
    path.write_text(json.dumps(work_meta, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_new_works(page, store, work_meta, today):
    """
    新着一覧ページから新作を取得し、発売日をwork_metaに蓄積する。
    ルール：
    1. タイトルに「配信開始は〇年〇月〇日」 → その日付を発売日として記録
    2. タイトルに日付がなし → 今日を発売日として記録
    3. 既に発売日が記録済みの作品 → 上書きしない
    """
    url = f"https://pokedora.com/products/list.php?order=1&store={store}"
    print(f"  新着一覧取得中: {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
    except Exception as e:
        print(f"  新着ページアクセス失敗: {e}")
        return work_meta

    soup = BeautifulSoup(page.content(), "html.parser")
    updated = 0

    for link in soup.select("a[href*='/products/detail.php']"):
        href = link.get("href", "")
        m = re.search(r"product_id=(\d+)", href)
        if not m:
            continue
        pid = m.group(1)

        # タイトル取得
        img_el = link.find("img")
        if img_el and img_el.get("alt", "").strip():
            title_raw = img_el.get("alt", "").strip()
        else:
            title_raw = link.get_text(separator=" ").strip()
        if not title_raw or len(title_raw) < 2:
            continue

        clean_title = re.sub(r"《?配信開始は[^》）]+[》）]?\s*", "", title_raw).strip()

        if pid not in work_meta:
            work_meta[pid] = {}

        # 初めて新着一覧で見つけた日を記録（予約開始日）
        if "registered_date" not in work_meta[pid]:
            work_meta[pid]["registered_date"] = today
            updated += 1
            # 発売予定日がない新作は今日が発売日
            dm = re.search(r"《?配信開始は(\d{4})年(\d{1,2})月(\d{1,2})日", title_raw)
            if not dm and "release_date" not in work_meta[pid]:
                work_meta[pid]["release_date"] = today

        # タイトルに発売予定日が含まれる場合はscheduled_dateとして記録（上書きしない）
        dm = re.search(r"《?配信開始は(\d{4})年(\d{1,2})月(\d{1,2})日", title_raw)
        if dm and "scheduled_date" not in work_meta[pid]:
            work_meta[pid]["scheduled_date"] = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

        work_meta[pid]["title"] = clean_title

    print(f"  発売日確定: {updated}件（累計: {len(work_meta)}件）")
    return work_meta

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
    # release_date・scheduled_dateを明示的に含めて保存
    output = []
    for w in works:
        entry = {
            "rank": w["rank"],
            "product_id": w["product_id"],
            "title": w["title"],
            "voice_actor": w.get("voice_actor", ""),
            "tags": w.get("tags", []),
            "thumb_url": w.get("thumb_url", ""),
            "work_url": w.get("work_url", ""),
            "store": w.get("store", store),
            "release_date": w.get("release_date", ""),
            "scheduled_date": w.get("scheduled_date", ""),
            "registered_date": w.get("registered_date", ""),
        }
        output.append(entry)
    json_str = json.dumps(output, ensure_ascii=False, indent=2)
    # data/（履歴保持用）
    (DATA_DIR / f"latest_{store}.json").write_text(json_str, encoding="utf-8")
    # docs/data/（GitHub Pages配信用）
    docs_data_dir = Path("docs") / "data"
    docs_data_dir.mkdir(parents=True, exist_ok=True)
    (docs_data_dir / f"latest_{store}.json").write_text(json_str, encoding="utf-8")

def update_history(history, store, today, works):
    """historyにその日のランキングを記録（product_id: rank の辞書形式）
    過去に記録された作品が今日ランキング外なら31（圏外）として記録する"""
    if store not in history:
        history[store] = {}

    today_ranked = {w["product_id"]: w["rank"] for w in works}

    # 過去に追跡していた全product_idを収集
    all_tracked_pids = set()
    for day_data in history[store].values():
        all_tracked_pids.update(day_data.keys())

    # 今日のデータ：ランキング入りは実rank、圏外は31
    today_data = {}
    for pid in all_tracked_pids:
        today_data[pid] = today_ranked.get(pid, 31)  # 31 = 圏外
    # 今日新たにランクインした作品も追加
    for pid, rank in today_ranked.items():
        today_data[pid] = rank

    history[store][today] = today_data

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
        # この作品が最初に記録された日付を取得
        first_date = None
        for d in dates:
            if pid in store_history.get(d, {}):
                first_date = d
                break

        for d in dates:
            day_data = store_history.get(d, {})
            if pid in day_data:
                ranks.append(day_data[pid])
            elif first_date and d > first_date:
                # 追跡開始後でデータなし = 圏外(31)
                ranks.append(31)
            else:
                # 追跡開始前 = 空白（グラフに表示しない）
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
    <div class="header-update">🔄 毎日23:30頃更新 ／ $today_str</div>
</div>

<div class="stat-row">
    <div class="stat-card">
        <div class="stat-label">📦 収録作品数</div>
        <div class="stat-value">$total_works</div>
        <div class="stat-sub">オトナ向けランキング</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">✨ 新着</div>
        <div class="stat-value">$new_today</div>
        <div class="stat-sub">$today_str</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">🔔 近日配信予定</div>
        <div class="stat-value">$rising_count</div>
        <div class="stat-sub">配信開始前の作品</div>
    </div>
</div>

$rising_section

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
            <tr><th></th><th>タイトル / 発売日 / ジャンル</th><th>声優</th><th>推移</th><th class="chart-cell">推移グラフ（30日）</th></tr>
        </thead>
        <tbody>
$ranking_rows
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
const graphData = $graph_data_json;
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
    url = w.get("thumb_url", "")
    if not url:
        url = f"https://pokedora.com/get_image.php?product_id={w['product_id']}"
    return f'<img src="{url}" alt="" loading="lazy">'

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
    title = re.sub(r'《?配信開始は[^》）]+[》）]?\s*', '', w['title']).strip()
    # 発売日確定済みなら「発売日」、発売予定日があれば「予約開始」で表示
    release_date = w.get("release_date", "")
    scheduled_date = w.get("scheduled_date", "")
    registered_date = w.get("registered_date", "")
    if release_date:
        date_span = f'<span class="work-date">発売日: {release_date}</span>'
    elif scheduled_date:
        date_span = f'<span class="work-date">発売予定日: {scheduled_date}</span>'
    else:
        date_span = ""
    return f"""        <tr>
            <td class="thumb-wrap">
                <span class="thumb-rank">{rb}</span>
                <a href="{w['work_url']}" target="_blank" rel="noopener">{th}</a>
            </td>
            <td class="title-cell">
                <div class="work-title"><a href="{w['work_url']}" target="_blank" rel="noopener">{title}</a></div>
                <div class="work-circle">{date_span}{w['voice_actor']}</div>
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

def extract_preorders(works, work_meta):
    """scheduled_dateが設定されている（発売予定日が未来の）作品を近日配信予定として抽出"""
    preorders = []
    # デバッグ：scheduled_dateを持つwork_metaエントリを確認
    scheduled_in_meta = {pid: v for pid, v in work_meta.items() if v.get("scheduled_date")}
    print(f"  [DEBUG] scheduled_date持ちの作品（work_meta）: {len(scheduled_in_meta)}件")
    for pid, v in list(scheduled_in_meta.items())[:3]:
        print(f"    pid={pid} scheduled={v.get('scheduled_date')} registered={v.get('registered_date')}")

    for w in works:
        pid = w["product_id"]
        scheduled = w.get("scheduled_date", "") or work_meta.get(pid, {}).get("scheduled_date", "")
        if scheduled:
            clean_title = re.sub(r'《?配信開始は[^》）]+[》）]?\s*', '', w["title"]).strip()
            registered = w.get("registered_date", "") or work_meta.get(pid, {}).get("registered_date", "")
            preorders.append({
                **w,
                "scheduled_date": scheduled,
                "registered_date": registered,
                "clean_title": clean_title,
            })
    preorders.sort(key=lambda x: x["scheduled_date"])
    return preorders[:5]


def make_preorder_row(w, index):
    pid = w["product_id"]
    title = w.get("clean_title", w["title"])
    scheduled_date = w.get("scheduled_date", "")
    registered_date = w.get("registered_date", "")
    url = w["work_url"]
    img_url = w.get("thumb_url", "")
    if not img_url:
        img_url = f"https://pokedora.com/get_image.php?product_id={pid}"
    voice = w.get("voice_actor", "")
    tags = w.get("tags", [])
    rb = f'<span class="rb rn">{index+1}</span>'
    tag_html = "".join(f'<span class="gtag">{t}</span>' for t in tags[:4])
    registered_span = f'<span class="work-date">予約開始: {registered_date}</span>' if registered_date else ""
    return f"""<tr>
            <td class="thumb-wrap">
                <span class="thumb-rank">{rb}</span>
                <a href="{url}" target="_blank" rel="noopener"><img src="{img_url}" alt="" loading="lazy"></a>
            </td>
            <td class="title-cell">
                <div class="work-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
                <div class="work-circle">{registered_span}{voice}</div>
                <div class="genres">{tag_html}</div>
            </td>
            <td style="font-size:11px;color:var(--text-sub)">{voice}</td>
            <td class="release-date-cell">{scheduled_date}</td>
        </tr>"""


def generate_html(ranking, preorders, graph_data, today_str, total_works, new_today, work_meta, today):
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
        # 新着 = 当日新着一覧で初めて登録された作品のみ
        is_new = work_meta.get(pid, {}).get("registered_date") == today
        ranking_rows.append(make_row(w, rank_change, is_new, f"wc_{i+1}"))

    # 近日配信予定セクション
    if preorders:
        rows = [make_preorder_row(w, i) for i, w in enumerate(preorders[:2])]
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
            <tr><th></th><th>タイトル / 予約開始日 / ジャンル</th><th>声優</th><th>発売予定日</th></tr>
        </thead>
        <tbody>
{"".join(rows)}
        </tbody>
    </table>
    </div>
</div>"""
    else:
        preorder_section = ""

    from string import Template
    html = Template(HTML_TEMPLATE).safe_substitute(
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

    store = "adt"
    history = load_history()

    # 新着一覧から発売日を先に取得・蓄積（ランキング作品への付与に使うため先行実行）
    work_meta = load_work_meta()
    with sync_playwright() as p_new:
        browser_new = p_new.chromium.launch()
        page_new = browser_new.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))
        work_meta = fetch_new_works(page_new, store, work_meta, today)
        browser_new.close()
    save_work_meta(work_meta)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))

        # オトナ向けのみメインページとして生成（がるまに方式に合わせる）
        label, url = CATEGORIES[store]
        print(f"\n--- {label} ---")

        works = fetch_ranking(page, store, url)
        browser.close()

    if not works:
        print("取得データなし・終了")
        return

    # ランキング作品にwork_metaから発売日情報を付与
    for w in works:
        pid = w["product_id"]
        meta_entry = work_meta.get(pid, {})

        scheduled = meta_entry.get("scheduled_date", "")
        registered = meta_entry.get("registered_date", "")
        release = meta_entry.get("release_date", "")

        # 旧形式（release_dateのみ、scheduled_date/registered_dateなし）の場合
        # タイトルから再解析してscheduled_dateを復元する
        if release and not scheduled and not registered:
            dm = re.search(r"《?配信開始は(\d{4})年(\d{1,2})月(\d{1,2})日", w["title"])
            if dm:
                # タイトルに配信開始日あり → 旧release_dateは誤り、scheduled_dateとして再設定
                scheduled = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
                work_meta[pid]["scheduled_date"] = scheduled
                work_meta[pid]["registered_date"] = release  # 旧release_dateを予約開始日として転用
                registered = release
                del work_meta[pid]["release_date"]
                release = ""
                print(f"  旧データ移行: {pid} scheduled={scheduled} registered={registered}")
            # タイトルに配信開始日なし → release_dateはそのまま発売日として正しい

        # 発売予定日を過ぎていれば発売日として確定
        if scheduled and today >= scheduled and not release:
            work_meta[pid]["release_date"] = scheduled
            release = scheduled
            print(f"  発売日確定: {pid} → {scheduled}")

        # 表示用フィールドを設定
        if release:
            w["release_date"] = release
            w["scheduled_date"] = ""
            w["registered_date"] = registered
        elif scheduled:
            w["release_date"] = ""
            w["scheduled_date"] = scheduled
            w["registered_date"] = registered
        else:
            # 発売日・発売予定日ともに不明 → 表示しない（勝手に確定させない）
            w["release_date"] = ""
            w["scheduled_date"] = ""
            w["registered_date"] = registered

    # work_metaを更新保存
    save_work_meta(work_meta)

    # JSON保存
    save_latest(store, works)
    history = update_history(history, store, today, works)
    save_history(history)

    # 前日データ
    prev_date = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_data = history.get(store, {}).get(prev_date, {})

    # 近日配信予定（タイトルに配信開始日を含む作品）
    preorders = extract_preorders(works, work_meta)

    # グラフデータ（TOP10 + 近日配信予定）
    all_pids = list(dict.fromkeys(
        [w["product_id"] for w in works[:10]] +
        [w["product_id"] for w in preorders]
    ))
    graph_data = build_graph_data(history, store, all_pids, today)

    # ranking-hub用：graph_dataを単体JSONとして保存
    graph_json = json.dumps(graph_data, ensure_ascii=False)
    # data/（履歴保持用）とdocs/data/（GitHub Pages配信用）の両方に保存
    (DATA_DIR / f"graph_{store}.json").write_text(graph_json, encoding="utf-8")
    docs_data_dir = Path("docs") / "data"
    docs_data_dir.mkdir(parents=True, exist_ok=True)
    (docs_data_dir / f"graph_{store}.json").write_text(graph_json, encoding="utf-8")
    print(f"  graph_{store}.json 保存完了（{len(graph_data)}件）")
    # 統計
    total_works = len(works)
    new_today = sum(1 for w in works if work_meta.get(w["product_id"], {}).get("registered_date") == today)

    # ranking-hub用：統計情報を単体JSONとして保存
    new_work_ids = [w["product_id"] for w in works if work_meta.get(w["product_id"], {}).get("registered_date") == today]
    meta = {
        "updated": today_str,
        "total_works": total_works,
        "new_today": new_today,
        "new_work_ids": new_work_ids,
        "preorder_count": len(preorders),
        "preorders": [
            {
                "id": w["product_id"],
                "title": w.get("clean_title", w["title"]),
                "voice_actor": w.get("voice_actor", ""),
                "release_date": w.get("scheduled_date", ""),   # 発売予定日
                "registered_date": w.get("registered_date", ""),  # 予約開始日
                "thumb_url": w["thumb_url"],
                "work_url": w["work_url"],
                "tags": w.get("tags", [])[:4],
            }
            for w in preorders
        ],
    }
    meta_json = json.dumps(meta, ensure_ascii=False)
    (DATA_DIR / f"meta_{store}.json").write_text(meta_json, encoding="utf-8")
    (Path("docs") / "data" / f"meta_{store}.json").write_text(meta_json, encoding="utf-8")
    print(f"  meta_{store}.json 保存完了（近日配信予定: {len(preorders)}件）")

    # HTML生成
    html = generate_html(works, preorders, graph_data, today_str, total_works, new_today, work_meta, today)

    # docs/index.html に出力（GitHub Pages用）
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"\n✅ docs/index.html 生成完了")

if __name__ == "__main__":
    run()
