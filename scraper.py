"""
work_meta.json の release_date を全削除するスクリプト

- 既存作品の誤った release_date をすべて消去
- scheduled_date は保持（配信予定日は残す）
- 今後は scraper.py がタイトルの配信日から正しく設定する

実行場所: pokedora-ranking-repo/ 直下で実行
"""
import json
from pathlib import Path

targets = [
    Path("data/work_meta.json"),
    Path("docs/data/work_meta.json"),
]

for path in targets:
    if not path.exists():
        print(f"スキップ（ファイルなし）: {path}")
        continue

    data = json.loads(path.read_text(encoding="utf-8"))
    cleared = 0

    for pid, meta in data.items():
        if "release_date" in meta:
            del data[pid]["release_date"]
            cleared += 1

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {path}: {cleared}件の release_date を削除（scheduled_date は保持）")

print("\n完了。git add / commit / push → Actions手動実行してください。")
