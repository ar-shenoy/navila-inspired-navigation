# Future Work

Ideas that could strengthen the project further.  
**None of these are required to run the current demo.**

---

## Near term (practical)

1. **More reliable structured commands**  
   Constrained decoding / JSON schema validation for optional VLM outputs so fewer parses fall back to heuristics.

2. **Simple evaluation harness**  
   Fixed start→goal pairs with:
   - success (within X meters)
   - path length / efficiency
   - collision count  
   Compare heuristic-only vs hybrid planner.

3. **Shareable hosted demo**  
   Deploy `app_map_v2.py` to a free host (e.g. Hugging Face Spaces) for one-click review.

4. **Richer map context**  
   Better summaries of nearby roads/POIs for the planner prompt without heavy live downloads.

---

## Medium term (research-leaning)

5. **Stronger open VLMs**  
   Local or Kaggle-friendly models (e.g. small Qwen2-VL / Phi-vision class) with navigation-style prompts — only if dependency cost stays acceptable for reviewers.

6. **Fine-tuning path**  
   QLoRA-style adaptation on public navigation instruction data (e.g. R2R-style corpora) so mid-level commands become more consistent. Requires GPU hours and careful scope control.

7. **Better local avoidance**  
   Lightweight reactive methods (e.g. simple DWA-style scoring) on top of OSRM corridors.

---

## Longer term (full stack)

8. **Full simulator bridge**  
   When NVIDIA GPU + Isaac Sim (or Habitat) access exists, reuse the same mid-level command interface so high-level planning and low-level locomotion can be swapped closer to NaVILA’s original setting.

9. **Real robot path**  
   Keep mid-level commands stable; replace the map controller with a real locomotion stack later.

---

## Priority suggestion

For internship / lab discussion, the highest leverage next steps are usually:

1. metrics on a small fixed test set  
2. clearer structured VLM outputs (if VLM is emphasized)  
3. hosted demo link  
4. simulator bridge only after hardware access is real

The current repository is intentionally scoped to a **working hierarchical map demo** under hardware limits, with a clear path upward rather than an unfinished claim of a full VLA system.
