from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.provenance import load_hf_provenance_config, resolve_hf_token
from huggingface_hub import HfApi, hf_hub_download
from tasks import specs as task_specs

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_HTML = Path(__file__).resolve().with_name("website.html")
ACTIVE_TASK_IDS = tuple(sorted(task_specs.load_task_ids()))
DIFFICULTY_COLUMNS = (
    ("very easy", "very_easy_1", "Very Easy (1)"),
    ("easy", "easy_2", "Easy (2)"),
    ("medium", "medium_3", "Medium (3)"),
    ("hard", "hard_4", "Hard (4)"),
    ("very hard", "very_hard_5", "Very Hard (5)"),
    ("extreme", "extreme_6", "Extreme (6)"),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _company_name(provider: str) -> str:
    provider_name = _text(provider).lower()
    if provider_name in {"openai", "pi", "codex"}:
        return "OpenAI"
    return provider_name.title() if provider_name else "Unknown"


def _agent_name(provider: str) -> str:
    provider_name = _text(provider).lower()
    if provider_name == "openai":
        return "none"
    if provider_name in {"pi", "codex"}:
        return provider_name
    return provider_name or "none"


def _has_web_access(access: str) -> bool:
    return _text(access).lower() in {"web", "web_ci"}


def _display_model_name(model: str, reasoning_effort: str) -> str:
    model_text = _text(model)
    effort_text = _text(reasoning_effort)
    if model_text and effort_text:
        return f"{model_text} {effort_text}"
    return model_text


@dataclass(frozen=True)
class ImportedReport:
    report: dict[str, Any]
    run_name: str
    source_path: str


def _collect_direct_reports(api: HfApi, repo_id: str) -> list[ImportedReport]:
    entries = list(
        api.list_repo_tree(
            repo_id=repo_id,
            repo_type="dataset",
            path_in_repo="evals/harnesses",
            recursive=True,
            token=resolve_hf_token(REPO_ROOT),
        )
    )
    reports: list[ImportedReport] = []
    for entry in entries:
        path_in_repo = _text(getattr(entry, "path", ""))
        if not path_in_repo.endswith("/report.json"):
            continue
        report_path = Path(
            hf_hub_download(
                repo_id=repo_id,
                repo_type="dataset",
                filename=path_in_repo,
                token=resolve_hf_token(REPO_ROOT),
            )
        )
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        reports.append(
            ImportedReport(
                report=payload,
                run_name=Path(path_in_repo).parent.name,
                source_path=f"hf://{repo_id}/{path_in_repo}",
            )
        )
    return reports


def _report_is_publishable(item: ImportedReport) -> bool:
    harness = item.report.get("harness", {})
    tasks = item.report.get("tasks", [])
    rows = item.report.get("rows", [])
    benchmark_task_count = item.report.get("benchmark_task_count")
    if not isinstance(harness, dict) or not isinstance(tasks, list) or not isinstance(rows, list):
        return False
    if not rows or len(rows) != len(ACTIVE_TASK_IDS):
        return False
    if int(benchmark_task_count or 0) != len(ACTIVE_TASK_IDS):
        return False
    task_ids = sorted(str(task_id) for task_id in tasks)
    if task_ids != list(ACTIVE_TASK_IDS):
        return False
    row_task_ids = sorted(str((row if isinstance(row, dict) else {}).get("task_id") or "") for row in rows)
    if row_task_ids != list(ACTIVE_TASK_IDS):
        return False
    for row in rows:
        if not isinstance(row, dict):
            return False
        if _text(row.get("error")):
            return False
        if _text(row.get("grader_error")):
            return False
        if _text(row.get("provenance_error")):
            return False
    return True


def _difficulty_summary(summary: dict[str, Any], name: str) -> float:
    by_difficulty = summary.get("by_difficulty", {})
    if not isinstance(by_difficulty, dict):
        return 0.0
    return _number(by_difficulty.get(name))


def _harness_row(item: ImportedReport) -> dict[str, Any]:
    report = item.report
    harness = report.get("harness", {})
    summary = report.get("summary", {})
    provider = _text(harness.get("provider"))
    model = _text(harness.get("model"))
    reasoning_effort = _text(harness.get("reasoning_effort"))
    access = _text(harness.get("access"))
    tasks = report.get("tasks", [])
    task_count = len(tasks) if isinstance(tasks, list) else 0
    return {
        "harness_id": _text(harness.get("id")),
        "company": _company_name(provider),
        "provider": provider,
        "agent": _agent_name(provider),
        "model": _display_model_name(model, reasoning_effort),
        "access": access,
        "web_access": _has_web_access(access),
        "reasoning_effort": reasoning_effort,
        "strategy": _text(harness.get("strategy")),
        "timestamp_utc": _text(report.get("timestamp_utc")),
        "run_name": item.run_name,
        "task_count": task_count,
        "overall": _number(summary.get("benchmark_score")),
        **{
            field_name: _difficulty_summary(summary, difficulty)
            for difficulty, field_name, _label in DIFFICULTY_COLUMNS
        },
    }


def _latest_publishable_reports(reports: list[ImportedReport]) -> list[ImportedReport]:
    selected: dict[str, ImportedReport] = {}
    for item in reports:
        if not _report_is_publishable(item):
            continue
        harness_id = _text((item.report.get("harness") or {}).get("id"))
        if not harness_id:
            continue
        current = selected.get(harness_id)
        item_key = (_text(item.report.get("timestamp_utc")), item.run_name)
        if current is None:
            selected[harness_id] = item
            continue
        current_key = (_text(current.report.get("timestamp_utc")), current.run_name)
        if item_key > current_key:
            selected[harness_id] = item
    return sorted(
        selected.values(),
        key=lambda value: (
            -_number((value.report.get("summary") or {}).get("benchmark_score")),
            _text((value.report.get("harness") or {}).get("id")),
        ),
    )


def _payload(reports: list[ImportedReport], repo_id: str) -> dict[str, Any]:
    harness_rows = [_harness_row(item) for item in _latest_publishable_reports(reports)]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_repo_id": repo_id,
        "source_prefix": "evals/harnesses",
        "total_harnesses": len(harness_rows),
        "harnesses": harness_rows,
    }


def _html_template(payload: dict[str, Any]) -> str:
    table_payload = [
        row for row in payload.get("harnesses", []) if isinstance(row, dict)
    ]
    table_payload.sort(
        key=lambda item: (-_number(item.get("overall")), _text(item.get("harness_id")))
    )
    payload_json = json.dumps(
        table_payload, separators=(",", ":"), ensure_ascii=True
    ).replace("</script>", "<\\/script>")
    toggle_html = "\n".join(
        f'        <label class="toggle"><input type="checkbox" data-column-toggle="{field_name}">{label}</label>'
        for _difficulty, field_name, label in DIFFICULTY_COLUMNS
    )
    difficulty_column_specs = ",\n      ".join(
        '{{title: "{label}", field: "{field_name}", sorter: "number", formatter: scoreFormatter, minWidth: 88, widthGrow: 1, widthShrink: 1, hozAlign: "left", headerFilter: "input", headerFilterFunc: percentHeaderFilter}}'.format(
            label=label,
            field_name=field_name,
        )
        for _difficulty, field_name, label in DIFFICULTY_COLUMNS
    )
    difficulty_fields = ", ".join(f'"{field_name}"' for _difficulty, field_name, _label in DIFFICULTY_COLUMNS)
    percent_fields = ", ".join(f'"{field_name}"' for _difficulty, field_name, _label in DIFFICULTY_COLUMNS)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EDA Bench Results</title>
  <meta name="color-scheme" content="light dark">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
  <link href="https://unpkg.com/tabulator-tables@6.3.1/dist/css/tabulator.min.css" rel="stylesheet">
  <style>
    :root {{
      color-scheme: light dark;
      font-family: "Inter", sans-serif;
      font-size: 18px;
      --table-scale: 1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: inherit;
      background: #fffaf6;
      color: #1f1712;
    }}
    .page {{
      width: 100%;
      padding: 16px 20px 24px;
    }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px 20px;
      align-items: center;
      margin-bottom: 16px;
    }}
    .tabulator .tabulator-header .tabulator-col .tabulator-col-content,
    .tabulator .tabulator-header .tabulator-col .tabulator-col-content .tabulator-col-title {{
      overflow: visible !important;
      text-overflow: clip !important;
    }}
    .tabulator .tabulator-header .tabulator-col .tabulator-col-content .tabulator-col-title {{
      width: 100%;
      white-space: nowrap !important;
      line-height: 1.1;
    }}
    .toggle-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 18px;
      align-items: center;
    }}
    .toggle {{
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      white-space: nowrap;
      cursor: pointer;
    }}
    .toggle input {{
      inline-size: 1rem;
      block-size: 1rem;
      margin: 0;
    }}
    .table-shell {{
      width: 100%;
      overflow-x: auto;
      overscroll-behavior-x: contain;
      -webkit-overflow-scrolling: touch;
      padding-right: 40px;
    }}
    #harness-table {{
      width: max-content;
      min-width: 0;
    }}
    .status {{
      margin-bottom: 12px;
      font-size: 0.95rem;
      color: #5d4032;
    }}
    .tabulator {{
      width: max-content;
      font-family: inherit;
      font-size: calc(0.95rem * var(--table-scale));
      border: 1px solid #ddd6ce;
      background: #fffdf9;
      color: inherit;
    }}
    .tabulator .tabulator-header {{
      background: #f5e6dc;
      border-bottom: 1px solid #d8b8a2;
      color: inherit;
    }}
    .tabulator .tabulator-header .tabulator-col {{
      font-size: calc(0.95rem * var(--table-scale));
      font-weight: 600;
      background: #f5e6dc;
      border-right: 0 !important;
      transition: background-color 120ms ease;
    }}
    .tabulator .tabulator-header .tabulator-col:hover {{
      background: #eed8c9;
    }}
    .tabulator .tabulator-header .tabulator-col .tabulator-header-filter {{
      margin-top: calc(0.35rem * var(--table-scale));
    }}
    .tabulator .tabulator-header .tabulator-col .tabulator-header-filter input,
    .tabulator .tabulator-header .tabulator-col .tabulator-header-filter select {{
      width: 100%;
      padding: calc(0.24rem * var(--table-scale)) calc(0.5rem * var(--table-scale));
      border: 1px solid #d8b8a2;
      border-radius: 0;
      background: #fffdf9;
      color: inherit;
      font: inherit;
    }}
    .tabulator .tabulator-row .tabulator-cell {{
      padding: calc(0.7rem * var(--table-scale)) calc(0.8rem * var(--table-scale));
      border-right: 0 !important;
      white-space: nowrap !important;
      overflow: visible !important;
      text-overflow: clip !important;
    }}
    .tabulator .tabulator-row {{
      background: #fffdf9;
      border-bottom: 1px solid #eee3da;
    }}
    .tabulator .tabulator-row:nth-child(even) {{
      background: #fff8ef;
    }}
    .tabulator .tabulator-row:hover {{
      background: #f4e3d6;
    }}
    @media (max-width: 640px) {{
      :root {{
        font-size: 16px;
      }}
      .page {{
        padding: 8px 8px 16px;
      }}
      .controls {{
        gap: 8px 12px;
        margin-bottom: 10px;
      }}
      .toggle-list {{
        gap: 8px 12px;
      }}
      .toggle {{
        gap: 0.35rem;
        font-size: 0.85rem;
      }}
      .toggle input {{
        inline-size: 0.9rem;
        block-size: 0.9rem;
      }}
      .tabulator {{
        width: 100%;
        font-size: calc(0.82rem * var(--table-scale));
      }}
      .tabulator .tabulator-header .tabulator-col {{
        font-size: calc(0.8rem * var(--table-scale));
      }}
      .tabulator .tabulator-header .tabulator-col .tabulator-col-content {{
        padding: 4px 1px 4px 3px;
      }}
      .tabulator .tabulator-header .tabulator-col .tabulator-header-filter input,
      .tabulator .tabulator-header .tabulator-col .tabulator-header-filter select {{
        padding: calc(0.16rem * var(--table-scale)) calc(0.18rem * var(--table-scale));
      }}
      .tabulator .tabulator-tableholder {{
        overflow-x: auto !important;
        overscroll-behavior-x: contain;
        touch-action: pan-x pan-y;
      }}
      .tabulator .tabulator-header .tabulator-col .tabulator-col-content .tabulator-col-sorter,
      .tabulator .tabulator-header .tabulator-col .tabulator-col-content .tabulator-col-sorter .tabulator-arrow {{
        display: none !important;
      }}
      .tabulator .tabulator-row .tabulator-cell {{
        padding: calc(0.4rem * var(--table-scale)) calc(0.22rem * var(--table-scale));
      }}
    }}
    @media (prefers-color-scheme: dark) {{
      body {{
        background: #18120e;
        color: #f3e6da;
      }}
      .tabulator {{
        background: #18120e;
        border-color: #6f4a34;
        color: #f3e6da;
      }}
      .tabulator .tabulator-header {{
        background: #302118;
        border-bottom-color: #7a5239;
        color: #f7e6d7;
      }}
      .tabulator .tabulator-header .tabulator-col {{
        background: #302118;
      }}
      .tabulator .tabulator-header .tabulator-col:hover,
      .tabulator .tabulator-header .tabulator-col.tabulator-sortable:hover {{
        background: #3b281d !important;
      }}
      .tabulator .tabulator-header .tabulator-col .tabulator-header-filter input,
      .tabulator .tabulator-header .tabulator-col .tabulator-header-filter select {{
        background: #18120e;
        border-color: #6f4a34;
        color: #f3e6da;
      }}
      .tabulator .tabulator-tableholder .tabulator-table {{
        background: #18120e;
        color: #f3e6da;
      }}
      .tabulator .tabulator-row {{
        background: #18120e;
        border-bottom-color: #2b2019;
      }}
      .tabulator .tabulator-row:nth-child(even) {{
        background: #1f1712;
      }}
      .tabulator .tabulator-row:hover {{
        background: #2b2019;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="controls" id="controls">
      <div class="toggle-list">
        <label class="toggle"><input type="checkbox" data-column-toggle="company">Company</label>
        <label class="toggle"><input type="checkbox" data-column-toggle="model">Model</label>
        <label class="toggle"><input type="checkbox" data-column-toggle="agent">Agent</label>
        <label class="toggle"><input type="checkbox" data-column-toggle="web_access">Internet</label>
        <label class="toggle"><input type="checkbox" data-column-toggle="overall">Overall</label>
{toggle_html}
      </div>
    </div>
    <div class="status" id="table-status">Loading results...</div>
    <div class="table-shell">
      <div id="harness-table"></div>
    </div>
  </div>

  <script id="payload" type="application/json">{payload_json}</script>
  <script src="https://unpkg.com/tabulator-tables@6.3.1/dist/js/tabulator.min.js"></script>
  <script>
    const allHarnesses = JSON.parse(document.getElementById("payload").textContent);
    let harnessTable = null;
    const tableStatus = document.getElementById("table-status");
    const columnToggles = Array.from(document.querySelectorAll("[data-column-toggle]"));

    function percentText(value) {{
      const number = Number(value);
      if (!Number.isFinite(number)) {{
        return "";
      }}
      const percent = number * 100;
      if (percent >= 99.9) {{
        return "100%";
      }}
      return `${{percent.toFixed(1)}}%`;
    }}

    function scoreFormatter(cell) {{
      const value = Number(cell.getValue() || 0);
      return percentText(value);
    }}

    function yesNoText(value) {{
      return value ? "" : "✓";
    }}

    function yesNoFormatter(cell) {{
      return yesNoText(Boolean(cell.getValue()));
    }}

    function textHeaderFilter(headerValue, rowValue) {{
      const needle = String(headerValue || "").trim().toLowerCase();
      if (!needle) {{
        return true;
      }}
      return String(rowValue ?? "").toLowerCase().includes(needle);
    }}

    function percentHeaderFilter(headerValue, rowValue) {{
      const needle = String(headerValue || "").trim().toLowerCase();
      if (!needle) {{
        return true;
      }}
      return percentText(rowValue).toLowerCase().includes(needle);
    }}

    function booleanHeaderFilter(headerValue, rowValue) {{
      const needle = String(headerValue || "").trim().toLowerCase();
      if (!needle) {{
        return true;
      }}
      if (["yes", "y", "true", "1", "check", "checked", "offline", "no web", "no checks", "✓"].includes(needle)) {{
        return !Boolean(rowValue);
      }}
      if (["no", "n", "false", "0", "uncheck", "unchecked", "web", "with web", "blank", "empty"].includes(needle)) {{
        return Boolean(rowValue);
      }}
      return false;
    }}

    const baseColumnSpecs = [
      {{title: "Company", field: "company", minWidth: 88, widthGrow: 1, widthShrink: 1, headerFilter: "input", headerFilterFunc: textHeaderFilter}},
      {{title: "Model", field: "model", minWidth: 128, widthGrow: 5, widthShrink: 3, headerFilter: "input", headerFilterFunc: textHeaderFilter}},
      {{title: "Agent", field: "agent", minWidth: 60, widthGrow: 1, widthShrink: 2, headerFilter: "input", headerFilterFunc: textHeaderFilter}},
      {{title: "Internet", field: "web_access", formatter: yesNoFormatter, minWidth: 54, widthGrow: 0, widthShrink: 1, hozAlign: "center", headerHozAlign: "center", headerFilter: "input", headerFilterFunc: booleanHeaderFilter}},
      {{title: "Overall", field: "overall", sorter: "number", formatter: scoreFormatter, minWidth: 68, width: 76, widthGrow: 0, widthShrink: 1, hozAlign: "left", headerFilter: "input", headerFilterFunc: percentHeaderFilter}},
      {difficulty_column_specs},
    ];
    const baseDefaultFields = ["model", "agent", "web_access", "overall", {difficulty_fields}];
    const compactDefaultFields = ["model", "agent", "web_access", "overall"];
    const mobileDefaultFields = ["model", "agent", "web_access", "overall"];
    const columnPrefsKey = "eda_bench_visible_columns";
    let userCustomizedColumns = false;
    let tableScale = 1;
    let fontsReadyApplied = false;
    const widthMeasureCanvas = document.createElement("canvas");
    const widthMeasureContext = widthMeasureCanvas.getContext("2d");

    function isMobileScreen() {{
      return window.matchMedia("(max-width: 640px)").matches;
    }}

    function tableAvailableWidth() {{
      const shell = document.querySelector(".table-shell");
      return Math.max(
        0,
        Math.floor(shell?.clientWidth || window.innerWidth || 0),
      );
    }}

    function rootFontSizePx() {{
      return Number.parseFloat(getComputedStyle(document.documentElement).fontSize || "16") || 16;
    }}

    function bodyFontSizePx(scale = tableScale) {{
      return rootFontSizePx() * (isMobileScreen() ? 0.82 : 0.95) * scale;
    }}

    function headerFontSizePx(scale = tableScale) {{
      return rootFontSizePx() * (isMobileScreen() ? 0.8 : 0.95) * scale;
    }}

    function horizontalCellPaddingPx(scale = tableScale) {{
      return rootFontSizePx() * (isMobileScreen() ? 0.5 : 1.6) * scale;
    }}

    function horizontalHeaderPaddingPx(scale = tableScale) {{
      return rootFontSizePx() * (isMobileScreen() ? 0.35 : 1.6) * scale;
    }}

    function measureTextWidth(text, font) {{
      if (!widthMeasureContext) {{
        return String(text || "").length * 8;
      }}
      widthMeasureContext.font = font;
      return widthMeasureContext.measureText(String(text || "")).width;
    }}

    function bodyFont(scale = tableScale) {{
      return `400 ${{bodyFontSizePx(scale)}}px ${{getComputedStyle(document.body).fontFamily}}`;
    }}

    function headerFont(scale = tableScale) {{
      return `600 ${{headerFontSizePx(scale)}}px ${{getComputedStyle(document.body).fontFamily}}`;
    }}

    function displayTextForField(field, value) {{
      if (field === "overall" || [{percent_fields}].includes(field)) {{
        return percentText(value);
      }}
      if (field === "web_access") {{
        return yesNoText(Boolean(value)) || " ";
      }}
      return String(value ?? "");
    }}

    function contentWidthForSpec(spec, scale = tableScale) {{
      const headerWidth = measureTextWidth(spec.title, headerFont(scale));
      const valueWidth = allHarnesses.reduce((maxWidth, row) => {{
        return Math.max(maxWidth, measureTextWidth(displayTextForField(spec.field, row?.[spec.field]), bodyFont(scale)));
      }}, 0);
      return Math.ceil(Math.max(headerWidth + horizontalHeaderPaddingPx(scale), valueWidth + horizontalCellPaddingPx(scale)));
    }}

    function resolvedWidthForSpec(spec, scale = tableScale) {{
      const minWidth = isMobileScreen() ? 0 : Number(spec.minWidth || 0) * scale;
      const fixedWidth = isMobileScreen() ? 0 : Number(spec.width || 0) * scale;
      const maxWidth = isMobileScreen() ? 0 : Number(spec.maxWidth || 0) * scale;
      let width = Math.max(minWidth, fixedWidth, contentWidthForSpec(spec, scale));
      if (maxWidth) {{
        width = Math.min(width, maxWidth);
      }}
      return Math.ceil(width);
    }}

    function minimumWidthForFields(fields, scale = tableScale) {{
      const enabled = new Set(fields);
      return baseColumnSpecs
        .filter((spec) => enabled.has(spec.field))
        .reduce((sum, spec) => sum + resolvedWidthForSpec(spec, scale), 0);
    }}

    function mobileScaleForFields(fields) {{
      const availableWidth = tableAvailableWidth();
      if (!availableWidth) {{
        return 1;
      }}
      const baseWidth = minimumWidthForFields(fields, 1);
      if (!baseWidth) {{
        return 1;
      }}
      return Math.max(0.62, Math.min(1, availableWidth / baseWidth));
    }}

    function applyTableScale(scale) {{
      tableScale = scale;
      document.documentElement.style.setProperty("--table-scale", scale.toFixed(4));
    }}

    function canFitFields(fields) {{
      const availableWidth = tableAvailableWidth();
      if (!availableWidth) {{
        return true;
      }}
      return minimumWidthForFields(fields) <= availableWidth;
    }}

    function preferredDefaultFields() {{
      if (isMobileScreen()) {{
        return mobileDefaultFields;
      }}
      return canFitFields(baseDefaultFields) ? baseDefaultFields : compactDefaultFields;
    }}

    function setToggleState(fields) {{
      const enabledFields = new Set(fields);
      for (const toggle of columnToggles) {{
        toggle.checked = enabledFields.has(toggle.dataset.columnToggle);
      }}
    }}

    function validSavedFields(fields) {{
      if (!Array.isArray(fields) || !fields.length) {{
        return [];
      }}
      const knownFields = new Set(baseColumnSpecs.map((spec) => spec.field));
      return fields.filter((field) => knownFields.has(String(field)));
    }}

    function loadSavedColumnFields() {{
      const raw = window.localStorage.getItem(columnPrefsKey);
      if (!raw) {{
        return [];
      }}
      return validSavedFields(JSON.parse(raw));
    }}

    function saveActiveColumnFields() {{
      window.localStorage.setItem(columnPrefsKey, JSON.stringify(activeColumnFields()));
    }}

    function applyInitialToggleState() {{
      const savedFields = loadSavedColumnFields();
      if (savedFields.length) {{
        userCustomizedColumns = true;
        setToggleState(savedFields);
        return;
      }}
      setToggleState(preferredDefaultFields());
    }}

    function activeColumnFields() {{
      return columnToggles
        .filter((toggle) => toggle.checked)
        .map((toggle) => toggle.dataset.columnToggle);
    }}

    function activeColumnSpecs() {{
      const fields = new Set(activeColumnFields());
      const specs = baseColumnSpecs
        .filter((spec) => fields.has(spec.field))
        .map((spec) => ({{...spec}}));
      if (!isMobileScreen()) {{
        applyTableScale(1);
        return specs.map((spec) => {{
          const desktopSpec = {{...spec}};
          delete desktopSpec.maxWidth;
          if (desktopSpec.field === "model") {{
            desktopSpec.minWidth = 280;
            desktopSpec.widthGrow = 7;
            desktopSpec.widthShrink = 1;
            delete desktopSpec.width;
          }} else if (desktopSpec.field === "agent") {{
            desktopSpec.minWidth = Math.max(90, Number(desktopSpec.minWidth || 0));
            desktopSpec.widthGrow = 1;
            desktopSpec.widthShrink = 1;
            delete desktopSpec.width;
          }} else if (desktopSpec.field === "web_access") {{
            desktopSpec.minWidth = 104;
            desktopSpec.width = 104;
            desktopSpec.widthGrow = 0;
            desktopSpec.widthShrink = 1;
          }} else {{
            desktopSpec.minWidth = Math.max(92, Number(desktopSpec.minWidth || 0));
            desktopSpec.widthGrow = 1;
            desktopSpec.widthShrink = 1;
            delete desktopSpec.width;
          }}
          return desktopSpec;
        }});
      }}
      const scale = mobileScaleForFields([...fields]);
      applyTableScale(scale);
      return specs.map((spec) => {{
        const width = resolvedWidthForSpec(spec, scale);
        return {{
          ...spec,
          width,
          minWidth: width,
          maxWidth: width,
          widthGrow: 0,
          widthShrink: 0,
        }};
      }});
    }}

    let tableReady = false;

    function buildTable() {{
      applyInitialToggleState();
      harnessTable = new Tabulator("#harness-table", {{
        data: allHarnesses,
        layout: "fitData",
        index: "harness_id",
        initialSort: [{{column: "overall", dir: "desc"}}],
        downloadRowRange: "active",
        columnDefaults: {{
          headerHozAlign: "left",
          vertAlign: "middle",
        }},
        columns: activeColumnSpecs(),
      }});
      harnessTable.on("tableBuilt", () => {{
        tableReady = true;
        tableStatus.textContent = `Showing ${{allHarnesses.length}} published harnesses`;
        syncAfterFontsReady();
        syncOptionalColumns();
      }});
    }}

    function syncOptionalColumns() {{
      if (!tableReady || !harnessTable) {{
        return;
      }}
      Promise.resolve(harnessTable.setColumns(activeColumnSpecs())).then(() => harnessTable.redraw(true));
    }}

    function syncAfterFontsReady() {{
      if (fontsReadyApplied || !document.fonts?.ready) {{
        return;
      }}
      document.fonts.ready.then(() => {{
        fontsReadyApplied = true;
        syncOptionalColumns();
      }});
    }}

    for (const toggle of columnToggles) {{
      toggle.addEventListener("change", () => {{
        userCustomizedColumns = true;
        saveActiveColumnFields();
        syncOptionalColumns();
      }});
    }}
    window.addEventListener("resize", () => {{
      if (!tableReady || !harnessTable) {{
        return;
      }}
      if (!userCustomizedColumns) {{
        const preferredFields = preferredDefaultFields();
        const activeFields = activeColumnFields();
        if (preferredFields.join("|") !== activeFields.join("|")) {{
          setToggleState(preferredFields);
          syncOptionalColumns();
          return;
        }}
      }}
      harnessTable.redraw(true);
    }});
    buildTable();
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh website/website.html from published HF provenance reports."
    )
    parser.parse_args()

    cfg = load_hf_provenance_config(REPO_ROOT)
    api = HfApi(token=resolve_hf_token(REPO_ROOT))
    reports = _collect_direct_reports(api, cfg.repo_id)
    payload = _payload(reports, cfg.repo_id)
    WEBSITE_HTML.write_text(_html_template(payload), encoding="utf-8")
    print(
        f"Imported {payload['total_harnesses']} harnesses from hf://{cfg.repo_id}/evals/harnesses"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
