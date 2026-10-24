"""Reproducible development retrieval cases, not an independent effectiveness study."""
import json
from datetime import datetime, timezone

from researchbridge.core import ROOT, SearchIndex, load_data

CASES = [
    ("用藥素養", "41726533"), ("骨折 行動應用", "41726541"),
    ("large language models caregiver", "41726516"), ("蛋白質", "41049045"),
    ("產後 保險", "41001595"), ("clinical trials skull base", "41140426"),
    ("dementia adversarial text", "40964651"), ("隱私 大型語言模型", "40963721"),
]


def evaluate():
    papers, _ = load_data()
    index = SearchIndex(papers)
    details, summary = [], []
    for mode in ["tfidf", "hybrid"]:
        ranks = []
        for query, target in CASES:
            results, expanded, _ = index.search(query, mode=mode, limit=5)
            ids = [p["pmid"] for p in results]
            rank = ids.index(target) + 1 if target in ids else None
            ranks.append(rank)
            details.append({"mode": mode, "query": query, "expanded": expanded, "expected_pmid": target, "returned_pmids": ids, "rank": rank})
        summary.append({"方法": mode, "案例數": len(CASES), "預期文獻在第一筆": sum(r == 1 for r in ranks), "預期文獻在前五筆": sum(r is not None for r in ranks), "MRR@5": round(sum(1 / r if r else 0 for r in ranks) / len(CASES), 3)})
    report = {"scope": "Fixed development cases; not held-out research or clinical evaluation.", "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "summary": summary, "details": details}
    (ROOT / "data" / "evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    evaluate()
