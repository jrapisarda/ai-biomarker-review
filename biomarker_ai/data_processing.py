"""Core data processing logic for biomarker analysis."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import pandas as pd
from tqdm import tqdm

from .config import AppConfig


EXPECTED_COLUMNS: Tuple[str, ...] = (
    "pair_id",
    "gene_a_name",
    "gene_b_name",
    "dz_ss_mean",
    "dz_ss_se",
    "dz_ss_ci_low",
    "dz_ss_ci_high",
    "dz_ss_i2",
    "n_studies_ss",
    "p_ss",
    "dz_soth_mean",
    "dz_soth_se",
    "kappa_ss",
    "kappa_soth",
    "total_samples",
    "eggers_p_ss",
    "publication_bias_ss",
    "combined_p_value",
    "power_score",
    "consistency_score",
    "control_weighted_r",
    "sepsis_weighted_r",
    "septic_shock_weighted_r",
    "sepsis_correlation",
    "shock_correlation",
    "correlation_delta",
    "corr_delta_abs",
    "corr_delta_relative",
    "is_amplification",
    "is_polarity_switch",
    "progression_slope",
    "correlation_pattern",
    "confidence_score",
    "uncertainty",
    "rationale",
    "model_version",
    "processing_timestamp",
    "is_statistically_sound",
)


@dataclass
class QualityIssue:
    pair_id: str
    issues: List[str]


@dataclass
class AnalysisResult:
    dataframe: pd.DataFrame
    quality_issues: List[QualityIssue]
    failed_rows: pd.DataFrame


NUMERIC_COLUMNS: Tuple[str, ...] = (
    "dz_ss_mean",
    "dz_ss_se",
    "dz_ss_ci_low",
    "dz_ss_ci_high",
    "dz_ss_i2",
    "n_studies_ss",
    "p_ss",
    "eggers_p_ss",
    "combined_p_value",
    "power_score",
    "consistency_score",
    "control_weighted_r",
    "sepsis_weighted_r",
    "septic_shock_weighted_r",
    "sepsis_correlation",
    "shock_correlation",
    "correlation_delta",
    "corr_delta_abs",
    "corr_delta_relative",
    "progression_slope",
    "confidence_score",
    "uncertainty",
)


MANDATORY_FIELDS: Tuple[str, ...] = (
    "pair_id",
    "p_ss",
    "dz_ss_mean",
    "confidence_score",
)


GENE_COLUMNS = ("gene_a_name", "gene_b_name")


def validate_structure(df: pd.DataFrame) -> List[str]:
    """Validate that the incoming DataFrame matches expectations."""

    errors: List[str] = []
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"Missing expected columns: {', '.join(missing)}")

    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    if extra:
        errors.append(f"Unexpected columns present: {', '.join(extra)}")

    return errors


def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    for column in NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _validate_range(row: pd.Series, config: AppConfig) -> List[str]:
    issues: List[str] = []
    thresholds = config.thresholds

    p_value = row.get("p_ss")
    if pd.isna(p_value) or not (0 <= p_value <= 1):
        issues.append("p_ss must be between 0 and 1")
    elif p_value > thresholds.max_p_value:
        issues.append(f"p_ss {p_value:.3g} exceeds max threshold {thresholds.max_p_value}")

    heterogeneity = row.get("dz_ss_i2")
    if pd.isna(heterogeneity) or not (0 <= heterogeneity <= 100):
        issues.append("dz_ss_i2 must be between 0 and 100")
    elif heterogeneity > thresholds.max_heterogeneity:
        issues.append(
            f"dz_ss_i2 {heterogeneity:.2f} exceeds max heterogeneity {thresholds.max_heterogeneity}"
        )

    n_studies = row.get("n_studies_ss")
    if pd.isna(n_studies) or n_studies < thresholds.min_studies:
        issues.append(
            f"n_studies_ss {n_studies} is below minimum {thresholds.min_studies}"
        )

    effect_size = row.get("dz_ss_mean")
    if pd.isna(effect_size) or abs(effect_size) < thresholds.min_effect_size:
        issues.append(
            f"dz_ss_mean {effect_size} does not meet minimum effect size {thresholds.min_effect_size}"
        )

    power_score = row.get("power_score")
    if pd.isna(power_score) or power_score < thresholds.min_power_score:
        issues.append(
            f"power_score {power_score} is below minimum {thresholds.min_power_score}"
        )

    return issues


def _validate_mandatory(row: pd.Series) -> List[str]:
    issues: List[str] = []
    for column in MANDATORY_FIELDS:
        if pd.isna(row.get(column)) or row.get(column) == "":
            issues.append(f"{column} is required")
    return issues


def _flag_gene_symbol(symbol: str) -> bool:
    if not symbol:
        return True
    clean = symbol.replace("-", "").replace("_", "")
    return not clean.isalnum() or not clean.isupper()


def _compute_statistical_score(row: pd.Series, config: AppConfig) -> float:
    thresholds = config.thresholds

    def clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    p_value = row.get("p_ss", 1)
    p_score = clamp(1 - (p_value / max(thresholds.max_p_value, 1e-6)))

    heterogeneity = row.get("dz_ss_i2", 100)
    heterogeneity_score = clamp(1 - (heterogeneity / max(thresholds.max_heterogeneity, 1e-6)))

    n_studies = row.get("n_studies_ss", thresholds.min_studies)
    studies_score = clamp((n_studies - thresholds.min_studies) / (thresholds.min_studies + 2))

    effect_size = abs(row.get("dz_ss_mean", 0))
    effect_score = clamp((effect_size - thresholds.min_effect_size) / (1.0 - thresholds.min_effect_size))

    power_score = row.get("power_score", thresholds.min_power_score)
    power_component = clamp((power_score - thresholds.min_power_score) / (1 - thresholds.min_power_score))

    return float((p_score + heterogeneity_score + studies_score + effect_score + power_component) / 5)


def _compute_biological_score(row: pd.Series) -> float:
    def clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    sepsis_corr = row.get("sepsis_correlation", 0)
    shock_corr = row.get("shock_correlation", 0)
    delta = abs(row.get("corr_delta_relative", 0))
    progression = row.get("progression_slope", 0)

    base_alignment = clamp((sepsis_corr + shock_corr) / 2)
    differential = clamp(1 - abs(delta))
    progression_component = clamp((progression + 1) / 2)

    return float((base_alignment + differential + progression_component) / 3)


def enrich_scores(df: pd.DataFrame, config: AppConfig) -> pd.DataFrame:
    """Add composite scores and categorical flags to the DataFrame."""

    stat_scores: List[float] = []
    bio_scores: List[float] = []
    for _, row in df.iterrows():
        stat_scores.append(_compute_statistical_score(row, config))
        bio_scores.append(_compute_biological_score(row))

    df = df.copy()
    df["statistical_score"] = stat_scores
    df["biological_score"] = bio_scores
    df["composite_score"] = (
        df["statistical_score"] * config.scoring.statistical
        + df["biological_score"] * config.scoring.biological
    )

    def classify(score: float) -> str:
        if score >= config.classification.green:
            return "Green"
        if score >= config.classification.amber:
            return "Amber"
        return "Red"

    df["classification"] = df["composite_score"].apply(classify)
    df["gene_symbol_flags"] = df.apply(
        lambda row: [
            symbol
            for symbol in GENE_COLUMNS
            if _flag_gene_symbol(str(row.get(symbol, "")))
        ],
        axis=1,
    )
    df["has_gene_symbol_issues"] = df["gene_symbol_flags"].apply(bool)
    return df


def process_dataset(
    df: pd.DataFrame,
    config: AppConfig,
    progress: bool = True,
) -> AnalysisResult:
    """Validate, score, and classify biomarker pairs."""

    structure_errors = validate_structure(df)
    if structure_errors:
        raise ValueError("; ".join(structure_errors))

    df = _coerce_numeric(df)

    quality_issues: List[QualityIssue] = []
    failed_rows: List[pd.Series] = []

    iterator: Iterable[pd.Series]
    if progress:
        iterator = tqdm(df.itertuples(index=False), total=len(df), desc="Validating")
    else:
        iterator = df.itertuples(index=False)

    for row_tuple in iterator:
        row = pd.Series(row_tuple._asdict())
        issues = _validate_mandatory(row) + _validate_range(row, config)
        gene_flags = [col for col in GENE_COLUMNS if _flag_gene_symbol(str(row.get(col, "")))]
        if gene_flags:
            issues.append(f"Potential gene symbol issue: {', '.join(gene_flags)}")

        if issues:
            quality_issues.append(QualityIssue(pair_id=str(row.get("pair_id")), issues=issues))
            failed_rows.append(row)

    scored_df = enrich_scores(df, config)

    failed_df = (
        pd.DataFrame(failed_rows, columns=df.columns)
        if failed_rows
        else pd.DataFrame(columns=df.columns)
    )
    if not failed_df.empty:
        failed_df = enrich_scores(failed_df, config)

    passed_df = scored_df[~scored_df["pair_id"].isin([issue.pair_id for issue in quality_issues])].copy()

    return AnalysisResult(dataframe=passed_df, quality_issues=quality_issues, failed_rows=failed_df)
