# Biomarker AI Analysis CLI

A command-line application that automates the review of gene-pair biomarker datasets, applies configurable statistical and biological checks, and generates Excel reports with AI-backed rationales. The tool fulfils the requirements described in `docs/RFC-Biomarker-AI-Analysis.md`.

## Model selection rationale

After surveying current model capabilities:

- **OpenAI GPT-5** offers state-of-the-art multimodal reasoning but does not expose tunable generation parameters such as temperature or maximum tokens in its public API, limiting fine-grained control for clinical reporting workflows.【8efde9†L7-L118】
- **Moonshot AI Kimi-K2-0905-Preview** provides an open Mixture-of-Experts model with strong reasoning, coding, and tool-use scores and, importantly, supports explicit `temperature` and `max_tokens` controls through its OpenAI-compatible API.【549ae3†L1-L118】【140e9e†L20-L73】

Because the biomarker analysis pipeline requires deterministic, configurable narratives and integration with tool-calling workflows, the application defaults to **Kimi-K2-0905-Preview** while retaining graceful fallbacks when API access is unavailable.

## Installation

1. Ensure Python 3.10 or later is installed.
2. (Recommended) Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install --upgrade pip
   pip install -e .
   ```
4. (Optional) Export the Kimi API key to enable live AI rationales:
   ```bash
   export KIMI_API_KEY="your-secret-key"
   ```

## Usage

Dump default configuration profiles:
```bash
biomarker-ai dump-profiles config_profiles
```

Run an analysis:
```bash
biomarker-ai run \
  --input docs/updated_biomarker_data_scored_sample.csv \
  --config configs/custom.yaml \
  --profile balanced \
  --output output/analysis.xlsx
```

### Key options

- `--config`: YAML file overriding threshold, scoring, API, or logging values.
- `--profile`: `conservative`, `balanced`, or `aggressive` default presets.
- `--dry-run`: Skip external AI calls while still generating deterministic rationales.
- `--disable-api`: Force offline mode even when API credentials exist.
- `--flagged-dir`: Destination for Markdown rationale reports on Amber/Red or failed pairs.

## Outputs

Running the tool creates:

- An Excel workbook with Summary, Detailed, FailedRows, QualityIssues, and Metadata sheets.
- Markdown rationale files for Amber/Red classifications and any rows that failed QC.
- Optional log files (when configured) under `logs/`.

## Configuration schema

Configuration files follow the structure in `biomarker_ai/config.py`. See the dumped profiles for examples. Important sections include `thresholds`, `scoring`, `classification`, `api_settings`, and `logging`.

## Development

Run linting and tests (if added) inside the virtual environment. The CLI is powered by [Typer](https://typer.tiangolo.com/) and uses pandas/tqdm for data handling and progress visualization.
