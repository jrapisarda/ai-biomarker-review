# AI-Powered Biomarker Screening Protocol  
*Outline for reviewing every row in `updated_biomarker_data_scored_sample.csv`*

---

## 1. Executive Summary
- **Goal**: Automatically flag gene-pairs that are *statistically sound* and *clinically promising* sepsis / septic-shock biomarkers.  
- **Approach**: Row-wise AI review that mimics an expert meta-analyst (stats-check → biological plausibility → progression signal → triage).  
- **Deliverable**: A living “Biomarker Short-list” table plus one-click rationale report for each candidate.

---

## 2. Data Ingestion & Sanity Pre-check
| Step | AI Action | Pass / Flag |
|---|---|---|
| 2.1 | Parse CSV → typed dataframe | dtype coercion errors |
| 2.2 | Assert mandatory fields | missing `pair_id`, `p_ss`, `dz_ss_mean`, `confidence_score` |
| 2.3 | Range & logic gates | `p_ss` &gt; 1 or &lt; 0; `I²` &lt; 0 or &gt; 100; `n_studies` &lt; 2 |
| 2.4 | Unit harmonisation | convert all effect sizes → Cohen’s d; CI → 95 % |

&gt; Auto-fix or quarantine rows that fail 2.2-2.4 → “Red-zone” table (do not proceed).

---

## 3. Statistical Credibility Engine
| Metric | Rule-of-Thumb Cut-off | AI Score (0-100) |
|---|---|---|
| **P-value** | p ≤ 0.001 (sepsis stratum) | 100 × −log₁₀(p) / 6 |
| **Effect size** | |d| ≥ 0.2 “small” | 100 if ≥ 0.4; linear ↓ |
| **Heterogeneity** | I² ≤ 50 % ideal | 100 − I² |
| **Consistency κ** | ≥ 0.6 | κ × 100 |
| **Egger bias test** | p ≥ 0.1 | 0 if p &lt; 0.05; 100 otherwise |
| **Power** | power_score ≥ 0.9 | power_score × 100 |

**Composite Stats-Score** = weighted average (weights user-tunable; defaults: P 30 %, ES 20 %, I² 20 %, κ 15 %, bias 10 %, power 5 %).

&gt; Rows with Stats-Score &lt; 50 → “Amber-zone” (needs human review).  
&gt; Rows with Stats-Score ≥ 70 AND `is_statistically_sound = TRUE` → auto-eligible for next stage.

---

## 4. Biological & Clinical Relevance Layer
| Feature | AI Query / Knowledge-Graph Step | Output |
|---|---|---|
| **Gene identity** | Map to Entrez, HGNC, UniProt | flag deprecated symbols |
| **Pathway overlap** | Enrichr API → sepsis, TLR, NF-κB, cytokine GO | hypergeometric p |
| **Tissue expression** | GTEx & HPA → immune cells, lung, liver | TPM z-score |
| **Protein–protein interaction** | STRING ≥ 700 confidence & edge-type | yes / no |
| **Mouse phenotype** | MGI lethal / immune / infection phenotype | binary |
| **Druggability** | DrugBank / Pharos target class | kinase, GPCR, etc. |

**Bio-Score** = logistic ensemble of above (pre-trained on historical biomarker successes).

---

## 5. Progression-Signal Detector
1. Compute Δ-correlation = `shock_correlation` − `sepsis_correlation`  
2. Classify pattern:  
   - Amplification-positive (Δ ≥ 0.15)  
   - Attenuation-negative (Δ ≤ –0.15)  
   - Stable (|Δ| &lt; 0.15)  
3. **Progression-Score** = |Δ| × 100 (capped 100)  
4. Optional ML: gradient-boosting trained on `progression_slope`, `corr_delta_relative`, `n_studies` to predict “AUC of future validation”.

---

## 6. Confidence Fusion & Triage
**Final_AI_Score** =  
0.45 × Stats-Score  
+ 0.30 × Bio-Score  
+ 0.25 × Progression-Score  

| Final_AI_Score | Tier | Action |
|---|---|---|
| ≥ 75 | **Green** | Auto-accept to short-list; generate 1-page report |
| 50-74 | **Amber** | Queue for curator review; AI highlights open issues |
| &lt; 50 | **Red** | Exclude; store rationale for audit |

---

## 7. Explainability Module (per row)
Auto-generated markdown report:


---

## 8. Human-in-the-Loop Review UI
- Sortable dashboard: Green / Amber / Red.  
- Quick-action buttons: “Promote”, “Demote”, “Request wet-lab follow-up”.  
- All curator decisions logged → reinforcement-learning feedback to re-calibrate weights.

---

## 9. Continuous Learning Loop
- Track later validations (true/false biomarker).  
- Periodically retrain Bio-Score and Final ensemble.  
- Store semantic embeddings of rationale text → improve auto-generated explanations.

---

## 10. Deliverables & Versioning
1. `AI_Biomarker_shortlist_master.csv` (living)  
2. `Row_wise_rationale_reports/` (markdown)  
3. `Model_card.yaml` (data version, cut-offs, AUROC, calibration curves)  
4. **Change-log** for every model or rule update (ISO time-stamp, author, diff).

---

> Ready for implementation in Python (pandas + scikit-learn + FastAPI) or R (tidyverse + tidymodels).  
> Estimated dev sprint: 3–4 weeks for MVP; 6-8 weeks for full UI & RL feedback.