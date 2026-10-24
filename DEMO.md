# ResearchBridge demo

Start with `run.cmd` or `python -m uvicorn app:app --host 127.0.0.1 --port 8000`.
Open http://127.0.0.1:8000. This is the FastAPI demo; `streamlit_app.py` is the
retained earlier interface.

## Three-minute walkthrough

1. **Check · 0:00–0:45.** “A researcher has a disease and a method. We compare
   their overall literature with early-detection literature.” Choose the saved
   **Obesity × Polymerase Chain Reaction** example. Explain the two counts and
   the ≤2-paper threshold. The badge explicitly identifies saved data.
2. **Brief · 0:45–1:20.** Choose **Build this brief**. Show that its title and
   counts match the selection. Open the exact query details and download Markdown.
   “This is a starting point for specialist review; a low indexed count does not
   prove novelty or that a method is effective.”
3. **Map · 1:20–2:00.** Choose a different disease from the shortlist, then build
   its brief. Show the 50 × 32 full-map option and the `cancer` filter. Ringed
   cells use saved PubMed counts; unringed cells lead to a new check.
4. **Method · 2:00–2:30.** Show the 79,940-paper corpus and withdrawn ranking
   claim. Explain that the measured bridge score did not improve selection, so
   candidates are ordered by overall paper counts. Historical validation is pending.
5. **Library · 2:30–3:00.** Show the separate starter-set search and its official
   abstract excerpt. Add a paper to comparison. Mention source checks and exports.

If time permits, return to Check and use **Refresh PubMed** to demonstrate a
dated live query. If PubMed is slow, use the saved map; it remains available
without a network connection. Do not describe the illustrative claim animation
as a working verification service, or present the institution directory as a
verified collaborator recommendation.

## Rehearsal checks

- Start the app from a fresh terminal using the documented command.
- Open each main tab; no content from another tab should remain visible.
- Select a saved example → Brief; compare the pairing, both counts and source badge.
- Edit either input → Brief; the previous pairing must be cleared.
- Select a different shortlist item → Brief; the new pairing must replace it.
- Download Markdown and inspect its queries; print preview should contain only the brief.
- Filter the map with `cancer`, then a nonsense word; clear it to restore the map.
- Search `zzxq987654xyz` in Library; confirm an empty state and then recover.
- Check the app at laptop width and at 390px, including dark appearance and keyboard navigation.

## Remaining product work

Verified Massachusetts collaborator matching, arbitrary claim verification and
corrected historical validation are future work. The submission demo delivers
a reproducible literature-check brief from saved or live PubMed counts.
