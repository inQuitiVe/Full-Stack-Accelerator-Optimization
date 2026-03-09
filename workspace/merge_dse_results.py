#!/usr/bin/env python3
"""
merge_dse_results.py — 合併 dse_22、dse_10_supplemental、dse_5_aggressive 並剔除重複。

重複判定：相同 params（hd_dim, reram, oc1, oc2, inner_dim, frequency, EDA flags 等）。
重複時優先保留：status=success > path3_failed > 其他；其次保留較新執行（supplemental > aggressive > main）。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

WORKSPACE = Path(__file__).parent

FILES = [
    ("dse_22_p1p2p3.json", "main"),
    ("dse_10_supplemental_p1p2p3.json", "supplemental"),
    ("dse_5_aggressive_p1p2p3.json", "aggressive"),
]


def _config_key(record: Dict[str, Any]) -> Tuple:
    """產生可 hash 的 config key，用於重複判定。"""
    p = record.get("params", {})
    exclude = {"synth_mode", "top_module"}
    items = sorted((k, v) for k, v in p.items() if k not in exclude)
    return tuple(items)


def _priority(record: Dict[str, Any], source: str) -> Tuple[int, int]:
    """回傳 (status_priority, source_priority)，數值越小越優先保留。"""
    status = record.get("status") or "unknown"
    status_rank = {"success": 0, "path2_only": 1, "path1_only": 2, "path3_failed": 3}
    status_priority = status_rank.get(status, 4)
    source_rank = {"supplemental": 0, "aggressive": 1, "main": 2}
    source_priority = source_rank.get(source, 3)
    return (status_priority, source_priority)


def main():
    all_results: List[Tuple[Dict[str, Any], str]] = []

    for filename, source in FILES:
        path = WORKSPACE / filename
        if not path.exists():
            print(f"[WARN] 跳過不存在的檔案: {path}")
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for r in data.get("results", []):
            all_results.append((r, source))

    # 依 config_key 去重，保留優先級最高者
    seen: Dict[Tuple, Tuple[Dict[str, Any], str]] = {}
    for record, source in all_results:
        key = _config_key(record)
        if key not in seen:
            seen[key] = (record, source)
        else:
            existing, ex_src = seen[key]
            if _priority(record, source) < _priority(existing, ex_src):
                seen[key] = (record, source)

    merged = [r for r, _ in seen.values()]

    # 剔除 fail 的實驗
    FAIL_STATUSES = {"gate1_failed", "gate2_failed", "path3_failed", "path1_error", "path2_error", "timeout", "error"}
    merged = [r for r in merged if (r.get("status") or "") not in FAIL_STATUSES]

    # 排序：先 group，再 frequency，再 inner_dim
    def _sort_key(r):
        p = r.get("params", {})
        g = r.get("group", "Z")
        f = p.get("frequency", 0)
        i = p.get("inner_dim", 0)
        return (g, f, i)

    merged.sort(key=_sort_key)

    # 重新編號 dp
    for i, r in enumerate(merged, start=1):
        r["dp"] = i

    # 舊資料 backfill：accuracy 來自 Path 1，補上 p1_accuracy 供顯示
    for r in merged:
        if "p1_accuracy" not in r and r.get("accuracy") is not None:
            r["p1_accuracy"] = r["accuracy"]

    meta = {
        "path2_enabled": True,
        "path3_enabled": True,
        "synth_mode": "fast",
        "top_module": "hd_top",
        "total_data_points": len(merged),
        "source_files": [f for f, _ in FILES if (WORKSPACE / f).exists()],
        "deduplicated": True,
        "failed_experiments_removed": True,
    }

    out_path = WORKSPACE / "dse_merged_p1p2p3.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "results": merged}, f, indent=2)

    print(f"合併完成: {len(merged)} 個實驗（已去重）")
    print(f"輸出: {out_path}")


if __name__ == "__main__":
    main()
