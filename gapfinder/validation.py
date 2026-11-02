"""The serving validation contract; exploratory reruns cannot approve a claim."""
from __future__ import annotations


def pending_validation(historical_analysis: dict | None = None) -> dict:
    state = {
        "schema_version": 1,
        "status": "pending_remeasurement",
        "withdrawn_claim": "2.0x lift of flagged gaps over unflagged",
        "withdrawn_because": [
            "corpus was 22% of the result set",
            "method axis had 14 terms, now 32 in the saved demo",
            "gap definition was corpus-scoped; 0 of 8 top gaps were real in full PubMed",
        ],
        "established_negative_result": {
            "claim": "mechanistic bridge score predicts a real gap",
            "verdict": False,
            "flagged_real": "368/475 = 77%",
            "rejected_real": "56/58 = 97%",
            "lift": 0.80,
            "recorded_date": "2026-10-24",
            "scope": "Historical saved-snapshot comparison; not a new build evaluation.",
        },
    }
    if historical_analysis is not None:
        state["historical_analysis"] = historical_analysis
        state["historical_analysis_scope"] = (
            "Exploratory corpus co-occurrence only. This does not revalidate the "
            "withdrawn lift or measure the full-PubMed gap definition."
        )
    return state


def serving_validation(payload: dict | None = None) -> dict:
    """Keep withdrawal evidence even when loading a legacy analysis JSON."""
    if payload is None:
        return pending_validation()
    if payload.get("schema_version") == 1 and payload.get("status") == "pending_remeasurement":
        return pending_validation(payload.get("historical_analysis"))
    return pending_validation(payload)
