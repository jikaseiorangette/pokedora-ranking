# ポケドラ ランキング分析

ポケットドラマCD（ポケドラ）の人気作品ランキングを毎日自動取得して表示するサイトです。

## 仕組み

```
GitHub Actions（毎日 JST 23:30）
  ↓
scraper.py 実行（Playwrightでポケドラをスクレイプ）
  ↓
data/history.json に履歴を蓄積
  ↓
docs/index.html を静的HTMLとして生成
  ↓
GitHub Pages で公開
```

**サーバー不要・完全無料**

## セットアップ

### 1. リポジトリ作成後、GitHub Pages を有効化

Settings → Pages → Source を **Deploy from a branch** に設定  
Branch: `main` / Folder: `/docs`

### 2. 手動で初回スクレイプ

Actions タブ → Daily Ranking Scrape → Run workflow

### 3. 以降は毎日 23:30 に自動実行

## ファイル構成

```
scraper.py                    # スクレイパー兼HTML生成
requirements.txt              # 依存パッケージ
.github/workflows/scrape.yml  # 自動実行スケジュール
data/
  history.json                # ランキング履歴（90日分）
  latest_adt.json             # 最新データ
docs/
  index.html                  # GitHub Pagesで公開されるHTML
```

## データソース

[ポケットドラマCD（ポケドラ）](https://pokedora.com) のランキングページより取得
