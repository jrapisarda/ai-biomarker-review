"""Configuration handling for the biomarker AI CLI."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class ThresholdSettings(BaseModel):
    """Statistical threshold configuration."""

    max_p_value: float = Field(..., gt=0, description="Maximum acceptable p-value")
    max_heterogeneity: float = Field(..., ge=0, le=100, description="Maximum acceptable I^2 value")
    min_studies: int = Field(..., ge=2, description="Minimum number of studies contributing to the meta-analysis")
    min_effect_size: float = Field(..., ge=0, description="Minimum Cohen's d effect size deemed clinically meaningful")
    min_power_score: float = Field(0.7, ge=0, le=1, description="Minimum acceptable statistical power score")


class ScoringWeights(BaseModel):
    """Weighting for statistical vs biological scoring."""

    statistical: float = Field(..., ge=0, le=1)
    biological: float = Field(..., ge=0, le=1)

    @field_validator("biological")
    @classmethod
    def validate_sum(cls, v: float, info: Any) -> float:
        other = info.data.get("statistical")
        if other is not None and abs((other + v) - 1.0) > 1e-6:
            raise ValueError("statistical and biological weights must sum to 1.0")
        return v


class ClassificationThresholds(BaseModel):
    """Thresholds for Green/Amber/Red classifications."""

    green: float = Field(0.75, ge=0, le=1)
    amber: float = Field(0.5, ge=0, le=1)

    @field_validator("amber")
    @classmethod
    def validate_order(cls, v: float, info: Any) -> float:
        green = info.data.get("green", 0.75)
        if v > green:
            raise ValueError("Amber threshold must be less than or equal to the green threshold")
        return v


class ApiSettings(BaseModel):
    """API connectivity options for the AI analysis layer."""

    base_url: str = Field("https://api.moonshot.cn/v1", description="Base URL for the Kimi API")
    model: str = Field("kimi-k2-0905-preview", description="Model identifier to request")
    temperature: float = Field(0.6, ge=0, le=1.5)
    max_tokens: int = Field(512, ge=1, le=8192)
    timeout: int = Field(60, ge=1)
    retry_attempts: int = Field(2, ge=0, le=5)
    fallback_mode: bool = True


class LoggingSettings(BaseModel):
    """Configuration for runtime logging."""

    level: str = Field("INFO")
    file: Optional[str] = None


class AppConfig(BaseModel):
    """Root configuration model."""

    thresholds: ThresholdSettings
    scoring: ScoringWeights
    classification: ClassificationThresholds = ClassificationThresholds()
    api_settings: ApiSettings = ApiSettings()
    logging: LoggingSettings = LoggingSettings()
    rationale_batch_size: int = Field(50, ge=1, le=200)
    enable_external_apis: bool = Field(True, description="Whether to attempt external enrichment APIs")


DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
    "balanced": {
        "thresholds": {
            "max_p_value": 0.01,
            "max_heterogeneity": 60.0,
            "min_studies": 3,
            "min_effect_size": 0.25,
            "min_power_score": 0.7,
        },
        "scoring": {"statistical": 0.5, "biological": 0.5},
    },
    "conservative": {
        "thresholds": {
            "max_p_value": 0.001,
            "max_heterogeneity": 40.0,
            "min_studies": 4,
            "min_effect_size": 0.35,
            "min_power_score": 0.8,
        },
        "scoring": {"statistical": 0.6, "biological": 0.4},
        "classification": {"green": 0.8, "amber": 0.6},
    },
    "aggressive": {
        "thresholds": {
            "max_p_value": 0.05,
            "max_heterogeneity": 75.0,
            "min_studies": 2,
            "min_effect_size": 0.15,
            "min_power_score": 0.6,
        },
        "scoring": {"statistical": 0.4, "biological": 0.6},
        "classification": {"green": 0.7, "amber": 0.45},
    },
}


def load_config(config_path: Optional[Path], profile: str | None = None) -> AppConfig:
    """Load configuration from file or default profiles."""

    data: Dict[str, Any]
    if config_path:
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    else:
        data = {}

    if profile:
        profile_key = profile.lower()
        if profile_key not in DEFAULT_PROFILES:
            raise ValueError(f"Unknown profile '{profile}'. Available: {', '.join(DEFAULT_PROFILES)}")
        profile_data = DEFAULT_PROFILES[profile_key]
    else:
        profile_data = DEFAULT_PROFILES["balanced"]

    merged: Dict[str, Any] = {**profile_data}
    for key, value in data.items():
        if isinstance(value, dict) and key in merged:
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value

    try:
        return AppConfig.model_validate(merged)
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration: {exc}") from exc


def dump_default_profiles(destination: Path) -> None:
    """Write default profiles to the destination directory for reference."""

    destination.mkdir(parents=True, exist_ok=True)
    for name, config in DEFAULT_PROFILES.items():
        path = destination / f"{name}.yaml"
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(config, fh, sort_keys=False)
