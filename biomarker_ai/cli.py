"""CLI entry point for the biomarker AI analysis application."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import typer

from .ai_analysis import AIAnalysisEngine
from .config import AppConfig, dump_default_profiles, load_config
from .data_processing import process_dataset
from .logging_utils import configure_logging
from .output import build_excel_report, write_flagged_rationales

LOGGER = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, help="AI-driven biomarker analysis CLI")


def _load_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise typer.BadParameter(f"Input file {path} does not exist")
    return pd.read_csv(path)


@app.command()
def dump_profiles(destination: Path = typer.Argument(Path("config_profiles"))):
    """Dump built-in threshold profiles for reference."""

    dump_default_profiles(destination)
    typer.echo(f"Profiles written to {destination}")


@app.command()
def run(
    input_file: Path = typer.Option(..., exists=True, readable=True, help="Input CSV containing biomarker pairs"),
    output_file: Path = typer.Option(Path("output/analysis.xlsx"), help="Destination Excel file"),
    config_file: Optional[Path] = typer.Option(None, help="Optional YAML configuration file"),
    profile: str = typer.Option("balanced", help="Default profile to use when configuration is partial"),
    disable_api: bool = typer.Option(False, help="Disable live AI calls even if credentials are available"),
    dry_run: bool = typer.Option(False, help="Skip AI rationales and only run validation/scoring"),
    progress: bool = typer.Option(True, help="Display progress bars"),
    flagged_dir: Path = typer.Option(Path("output/rationales"), help="Directory for flagged rationale reports"),
    include_failed: bool = typer.Option(
        True,
        help="Process all rows through the AI, including those that failed validation",
    ),
):
    """Execute the biomarker analysis pipeline."""

    config: AppConfig = load_config(config_file, profile=profile)
    log_path = configure_logging(config.logging)
    LOGGER.info("Starting biomarker analysis run")

    df = _load_dataset(input_file)
    result = process_dataset(df, config, progress=progress)
    LOGGER.info("Validated %s rows. %s failed quality checks.", len(df), len(result.failed_rows))

    records = result.dataframe.to_dict(orient="records")
    if include_failed and not result.failed_rows.empty:
        LOGGER.info(
            "Including %s quality-failed rows for rationale generation",
            len(result.failed_rows),
        )
        failed_records = result.failed_rows.to_dict(orient="records")
        for record in failed_records:
            record.setdefault("classification", "Quality Review")
            record.setdefault("composite_score", 0.0)
        records.extend(failed_records)
    elif not include_failed and not result.failed_rows.empty:
        LOGGER.info(
            "Skipping %s quality-failed rows from AI processing per configuration",
            len(result.failed_rows),
        )
    ai_engine = AIAnalysisEngine(
        config,
        enable_api=False if dry_run else not disable_api,
    )

    if dry_run:
        LOGGER.warning("Dry-run enabled: using deterministic offline rationales")
    elif disable_api:
        LOGGER.info("External AI disabled by flag; using offline rationales")

    rationales = ai_engine.generate_rationales(records)
    LOGGER.info("Generated %s rationales", len(rationales))

    metadata = {
        "input_file": str(input_file),
        "output_file": str(output_file),
        "config_file": str(config_file) if config_file else "<default>",
        "profile": profile,
        "dry_run": str(dry_run),
        "include_failed": str(include_failed),
        "timestamp": datetime.utcnow().isoformat(),
        "log_file": str(log_path) if log_path else "",
    }

    build_excel_report(result, rationales, output_file, config, metadata)
    write_flagged_rationales(rationales, result, flagged_dir)

    typer.echo("Analysis completed successfully")
    raise typer.Exit(code=0)


if __name__ == "__main__":  # pragma: no cover
    app()
