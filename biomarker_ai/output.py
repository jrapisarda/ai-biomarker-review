"""Excel report generation and artefact writing."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd

from .ai_analysis import Rationale
from .config import AppConfig
from .data_processing import AnalysisResult


def _summary_frame(enriched: pd.DataFrame) -> pd.DataFrame:
    classification_counts = enriched["classification"].value_counts().to_dict()
    summary = {
        "total_pairs": len(enriched),
        "green_count": classification_counts.get("Green", 0),
        "amber_count": classification_counts.get("Amber", 0),
        "red_count": classification_counts.get("Red", 0),
        "mean_composite": enriched["composite_score"].mean() if not enriched.empty else 0,
        "median_composite": enriched["composite_score"].median() if not enriched.empty else 0,
    }
    return pd.DataFrame([summary])


def build_excel_report(
    result: AnalysisResult,
    rationales: Iterable[Rationale],
    output_path: Path,
    config: AppConfig,
    metadata: Dict[str, str],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rationale_map = {r.pair_id: r for r in rationales}
    enriched = result.dataframe.copy()
    enriched["ai_rationale"] = enriched["pair_id"].map(lambda pid: rationale_map.get(pid, Rationale(pid, "", {})).text)

    summary_df = _summary_frame(enriched)
    quality_df = pd.DataFrame(
        (
            {
                "pair_id": issue.pair_id,
                "issues": "; ".join(issue.issues),
            }
            for issue in result.quality_issues
        )
    )

    metadata_df = pd.DataFrame(
        {
            "config": [json.dumps(config.model_dump(), indent=2)],
            "run_metadata": [json.dumps(metadata, indent=2)],
        }
    )

    failed_rows_df = (
        result.failed_rows
        if not result.failed_rows.empty
        else pd.DataFrame(columns=result.dataframe.columns)
    )

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        enriched.to_excel(writer, sheet_name="Detailed", index=False)
        failed_rows_df.to_excel(writer, sheet_name="FailedRows", index=False)
        quality_df.to_excel(writer, sheet_name="QualityIssues", index=False)
        metadata_df.to_excel(writer, sheet_name="Metadata", index=False)


def write_flagged_rationales(
    rationales: Iterable[Rationale],
    result: AnalysisResult,
    destination: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    flagged_ids = set(result.failed_rows["pair_id"].astype(str))
    amber_red = set(result.dataframe[result.dataframe["classification"] != "Green"]["pair_id"].astype(str))
    focus_ids = flagged_ids | amber_red

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for rationale in rationales:
        if rationale.pair_id not in focus_ids:
            continue
        file_path = destination / f"{timestamp}_{rationale.pair_id}.md"
        with file_path.open("w", encoding="utf-8") as fh:
            fh.write(f"# Gene Pair {rationale.pair_id}\n\n")
            fh.write(rationale.text)
            if rationale.metadata:
                fh.write("\n\n---\n")
                fh.write(json.dumps(rationale.metadata, indent=2))
