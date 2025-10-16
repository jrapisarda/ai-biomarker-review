"""AI rationale generation and external enrichment handling."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import requests

from .config import AppConfig

LOGGER = logging.getLogger(__name__)


@dataclass
class Rationale:
    pair_id: str
    text: str
    metadata: Dict[str, str]


class KimiModelClient:
    """Thin HTTP client for the Moonshot Kimi API."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        api_key = os.getenv("KIMI_API_KEY")
        if not api_key:
            raise RuntimeError("KIMI_API_KEY environment variable is required for live analysis")
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def generate(self, prompts: List[Dict[str, str]]) -> List[str]:
        url = f"{self.config.api_settings.base_url}/chat/completions"
        payload = {
            "model": self.config.api_settings.model,
            "temperature": self.config.api_settings.temperature,
            "max_tokens": self.config.api_settings.max_tokens,
            "messages": prompts,
        }

        for attempt in range(self.config.api_settings.retry_attempts + 1):
            try:
                response = self._session.post(
                    url,
                    headers=self._headers(),
                    data=json.dumps(payload),
                    timeout=self.config.api_settings.timeout,
                )
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                return [choice.get("message", {}).get("content", "") for choice in choices]
            except Exception as exc:  # pragma: no cover - network error path
                LOGGER.warning("Kimi API request failed on attempt %s: %s", attempt + 1, exc)
                if attempt >= self.config.api_settings.retry_attempts:
                    raise
                time.sleep(2 ** attempt)
        return []


def _fallback_rationale(row: Dict[str, object]) -> str:
    """Generate a deterministic rationale when API access is unavailable."""

    sections = [
        f"Pair {row.get('pair_id')} features genes {row.get('gene_a_name')} and {row.get('gene_b_name')}.",
        (
            "Statistical review: p_ss={p:.3g}, I²={i2:.1f}, effect={effect:.2f}, power={power:.2f}."
        ).format(
            p=row.get("p_ss", float("nan")),
            i2=row.get("dz_ss_i2", float("nan")),
            effect=row.get("dz_ss_mean", float("nan")),
            power=row.get("power_score", float("nan")),
        ),
        (
            "Clinical progression metrics indicate sepsis correlation {sepsis:.2f} and shock correlation {shock:.2f} with progression slope {slope:.2f}."
        ).format(
            sepsis=row.get("sepsis_correlation", float("nan")),
            shock=row.get("shock_correlation", float("nan")),
            slope=row.get("progression_slope", float("nan")),
        ),
        "Recommendation: prioritise for further review based on composite scoring and domain thresholds.",
    ]
    return " \n".join(sections)


class AIAnalysisEngine:
    """Coordinate AI-driven rationale creation with graceful fallbacks."""

    def __init__(self, config: AppConfig, enable_api: bool = True) -> None:
        self.config = config
        self.enable_api = enable_api and config.enable_external_apis
        self._client: Optional[KimiModelClient] = None
        if self.enable_api:
            try:
                self._client = KimiModelClient(config)
            except RuntimeError as exc:
                LOGGER.warning("Disabling live AI analysis: %s", exc)
                self.enable_api = False

    def generate_rationales(self, rows: Iterable[Dict[str, object]]) -> List[Rationale]:
        rationales: List[Rationale] = []
        batch: List[Dict[str, object]] = []
        for row in rows:
            batch.append(row)
            if len(batch) >= self.config.rationale_batch_size:
                rationales.extend(self._process_batch(batch))
                batch = []
        if batch:
            rationales.extend(self._process_batch(batch))
        return rationales

    def _process_batch(self, batch: List[Dict[str, object]]) -> List[Rationale]:
        if not batch:
            return []

        prompts: List[str] = [self._build_prompt(row) for row in batch]

        api_texts: List[Optional[str]] = [None] * len(batch)
        used_api_flags: List[bool] = [False] * len(batch)
        if self.enable_api and self._client:
            system_message = {"role": "system", "content": self._system_prompt()}
            for idx, prompt in enumerate(prompts):
                if not self.enable_api:
                    break
                try:
                    response = self._client.generate([system_message, {"role": "user", "content": prompt}])
                    if response:
                        api_texts[idx] = response[0]
                        used_api_flags[idx] = True
                except Exception as exc:  # pragma: no cover - network error path
                    LOGGER.error("Falling back to offline rationale due to API error: %s", exc)
                    self.enable_api = False
                    break

        results: List[Rationale] = []
        for idx, row in enumerate(batch):
            text = api_texts[idx] if idx < len(api_texts) else None
            used_api = used_api_flags[idx] if idx < len(used_api_flags) else False
            if not text:
                text = _fallback_rationale(row)
                used_api = False
            results.append(
                Rationale(
                    pair_id=str(row.get("pair_id")),
                    text=text,
                    metadata={
                        "model": self.config.api_settings.model,
                        "used_api": str(used_api),
                    },
                )
            )
        return results

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are an expert sepsis biomarker analyst. Summarise statistical validity, biological plausibility, "
            "clinical trajectory, and provide a clear recommendation with next steps."
        )

    @staticmethod
    def _build_prompt(row: Dict[str, object]) -> str:
        return (
            "Analyse the following gene pair. Provide a concise but detailed rationale covering statistical quality, "
            "biological plausibility, and clinical progression cues. Include a recommendation (proceed/review/reject).\n"
            f"Pair ID: {row.get('pair_id')}\n"
            f"Genes: {row.get('gene_a_name')} vs {row.get('gene_b_name')}\n"
            f"p_ss: {row.get('p_ss')}\n"
            f"I2: {row.get('dz_ss_i2')}\n"
            f"Effect size (Cohen's d): {row.get('dz_ss_mean')}\n"
            f"Power score: {row.get('power_score')}\n"
            f"Sepsis correlation: {row.get('sepsis_correlation')}\n"
            f"Shock correlation: {row.get('shock_correlation')}\n"
            f"Progression slope: {row.get('progression_slope')}\n"
            f"Composite score: {row.get('composite_score')}\n"
            f"Classification: {row.get('classification')}"
        )
