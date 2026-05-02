"""Statement upload parsing & analysis.

Supports PDF (bank/payer statements), CSV and XLS/XLSX (GL exports, AR aging,
payer remits). The output is a structured `summary_json` saved on the
`uploads` row and returned to the agent via the `analyze_uploaded_statement`
tool. The agent then composes recommendations grounded in this summary.
"""
from __future__ import annotations

import io
import json
import os
import re
import statistics
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.db import get_db


UPLOAD_ROOT = Path(os.environ.get("UPLOAD_DIR", "/data/uploads"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_MIME = {
    "application/pdf": "pdf",
    "text/csv": "csv",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}
ALLOWED_EXT = {".pdf": "pdf", ".csv": "csv", ".xls": "xls", ".xlsx": "xlsx"}
MAX_BYTES = 25 * 1024 * 1024  # 25 MB cap


# ---------- Persistence ----------

def save_upload(*, tenant_id: str, user_id: str, conversation_id: Optional[str],
                filename: str, mime: str, content: bytes) -> dict:
    if len(content) > MAX_BYTES:
        raise ValueError(f"file too large ({len(content)} bytes); max {MAX_BYTES}")
    ext = Path(filename).suffix.lower()
    fmt = ALLOWED_MIME.get(mime) or ALLOWED_EXT.get(ext)
    if not fmt:
        raise ValueError(f"unsupported file type: mime={mime} ext={ext}")

    uid = "up_" + uuid.uuid4().hex[:14]
    tenant_dir = UPLOAD_ROOT / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    path = tenant_dir / f"{uid}{ext or '.' + fmt}"
    path.write_bytes(content)

    # Parse and classify; on failure keep the upload but mark status=failed.
    summary: Optional[dict] = None
    err: Optional[str] = None
    kind = "generic"
    try:
        summary = parse(path, fmt)
        kind = summary.get("kind") or "generic"
    except Exception as e:  # pragma: no cover - parse failures should be rare
        err = str(e)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO uploads
               (id, tenant_id, user_id, conversation_id, filename, mime, size_bytes,
                storage_path, kind, status, parse_error, summary_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (uid, tenant_id, user_id, conversation_id, filename, mime, len(content),
             str(path), kind,
             "parsed" if summary else "failed",
             err, json.dumps(summary, default=str) if summary else None),
        )
    return {
        "id": uid,
        "filename": filename,
        "kind": kind,
        "status": "parsed" if summary else "failed",
        "size_bytes": len(content),
        "summary": summary,
        "parse_error": err,
    }


def get_upload(tenant_id: str, upload_id: str) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, filename, mime, size_bytes, kind, status, parse_error, summary_json, created_at "
            "FROM uploads WHERE id = %s AND tenant_id = %s",
            (upload_id, tenant_id),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["summary"] = json.loads(out.pop("summary_json")) if out.get("summary_json") else None
    return out


def list_uploads(tenant_id: str, user_id: Optional[str] = None,
                 conversation_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    sql = ("SELECT id, filename, kind, status, size_bytes, created_at FROM uploads "
           "WHERE tenant_id = %s")
    params: list[Any] = [tenant_id]
    if user_id:
        sql += " AND user_id = %s"; params.append(user_id)
    if conversation_id:
        sql += " AND conversation_id = %s"; params.append(conversation_id)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------- Parsing ----------

def parse(path: Path, fmt: str) -> dict:
    if fmt == "pdf":
        return _parse_pdf(path)
    if fmt == "csv":
        df = pd.read_csv(path)
        return _classify_dataframe(df, source=path.name)
    if fmt in ("xls", "xlsx"):
        return _parse_excel(path)
    return {"kind": "generic", "rows": 0, "note": f"unsupported format {fmt}"}


def _parse_excel(path: Path) -> dict:
    """Multi-sheet Excel parser. Detects financial models, GL extracts, AR aging,
    payer remittance and bank statements; for true financial models it returns a
    rich per-sheet shape so the agent can reason cross-sheet.
    """
    try:
        sheets = pd.read_excel(path, sheet_name=None)
    except Exception as e:
        return {"kind": "generic", "note": f"could not read workbook: {e}"}
    if not sheets:
        return {"kind": "generic", "rows": 0, "note": "empty workbook"}

    sheet_summaries: list[dict] = []
    classifier_hits: dict[str, int] = {}
    year_pattern = re.compile(r"\b20[2-3]\d\b")
    fin_keywords = (
        "revenue", "ebitda", "opex", "capex", "npv", "irr", "dcf",
        "terminal value", "wacc", "valuation", "projection", "forecast",
        "assumptions", "summary", "p&l", "income statement", "cash flow",
        "balance sheet", "scenario",
    )

    for sname, df in sheets.items():
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        try:
            kind_guess = _classify_dataframe(df, source=f"{path.name}::{sname}").get("kind", "generic")
        except Exception:
            kind_guess = "generic"
        classifier_hits[kind_guess] = classifier_hits.get(kind_guess, 0) + 1

        # Numeric snapshot per sheet (cap to avoid huge payloads)
        numeric_cols: dict[str, dict] = {}
        for c in list(df.columns)[:30]:
            vals = [_to_number(v) for v in df[c].tolist()]
            vals = [v for v in vals if v is not None]
            if len(vals) >= 3:
                numeric_cols[c] = {
                    "n": len(vals),
                    "sum": round(sum(vals), 2),
                    "mean": round(statistics.mean(vals), 2),
                    "min": round(min(vals), 2),
                    "max": round(max(vals), 2),
                }

        # Detect year-headed projection tables
        years_in_header = sorted({m.group(0) for c in df.columns for m in [year_pattern.search(str(c))] if m})
        # Sample first 3 non-empty cells to give the LLM textual context
        sample_cells: list[str] = []
        for _, row in df.head(8).iterrows():
            for v in row.tolist():
                if isinstance(v, str) and v.strip() and len(sample_cells) < 12:
                    sample_cells.append(v.strip()[:80])

        sheet_summaries.append({
            "sheet": sname,
            "rows": int(len(df)),
            "columns": list(df.columns)[:30],
            "years_in_header": years_in_header,
            "numeric_columns": numeric_cols,
            "sample_text": sample_cells,
            "kind_guess": kind_guess,
        })

    # Workbook-level kind decision
    joined_text = (" ".join(s.get("sheet", "") for s in sheet_summaries) + " "
                   + " ".join(" ".join(s.get("sample_text") or []) for s in sheet_summaries)).lower()
    fin_hits = sum(1 for k in fin_keywords if k in joined_text)
    has_year_projections = sum(1 for s in sheet_summaries if len(s.get("years_in_header") or []) >= 2)

    if (len(sheet_summaries) >= 4 and (fin_hits >= 3 or has_year_projections >= 2)):
        kind = "financial_model"
    else:
        # If the largest sheet matches a specific kind, promote that
        kind = max(classifier_hits, key=classifier_hits.get) if classifier_hits else "generic"

    # Headline metrics for financial models
    headline: dict[str, Any] = {}
    if kind == "financial_model":
        # Pull the largest numeric sums across all sheets, label by sheet/column
        flat: list[tuple[str, str, float]] = []
        for s in sheet_summaries:
            for col, stat in (s.get("numeric_columns") or {}).items():
                flat.append((s["sheet"], col, float(stat.get("sum") or 0)))
        flat.sort(key=lambda t: abs(t[2]), reverse=True)
        headline["largest_numeric_aggregates"] = [
            {"sheet": s, "column": c, "sum": round(v, 2)} for s, c, v in flat[:10]
        ]
        headline["sheet_count"] = len(sheet_summaries)
        headline["projection_sheets"] = [s["sheet"] for s in sheet_summaries if s.get("years_in_header")]
        headline["detected_keywords"] = [k for k in fin_keywords if k in joined_text][:12]

    return {
        "kind": kind,
        "sheets": [s["sheet"] for s in sheet_summaries],
        "sheet_count": len(sheet_summaries),
        "per_sheet": sheet_summaries,
        "headline": headline,
        "source": path.name,
    }


def _parse_pdf(path: Path) -> dict:
    try:
        import pdfplumber  # type: ignore
    except Exception:
        return {"kind": "generic", "note": "pdfplumber not installed"}

    text_parts: list[str] = []
    table_rows: list[list[str]] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages[:30]:  # cap at 30 pages
            try:
                t = page.extract_text() or ""
                if t:
                    text_parts.append(t)
            except Exception:
                pass
            try:
                for table in page.extract_tables() or []:
                    for row in table:
                        clean = [(c or "").strip() for c in row]
                        if any(clean):
                            table_rows.append(clean)
            except Exception:
                pass

    text = "\n".join(text_parts)
    summary: dict[str, Any] = {
        "kind": "bank_statement" if _looks_like_bank_statement(text) else "generic",
        "page_count": len(text_parts),
        "char_count": len(text),
        "sample_text": text[:1500],
        "tables_extracted": len(table_rows),
    }
    if table_rows:
        # Try to coerce the largest table into a dataframe
        try:
            df = _rows_to_df(table_rows)
            classified = _classify_dataframe(df, source=path.name)
            # Preserve the kind from text-detection if it was bank_statement
            if summary["kind"] == "bank_statement" and classified["kind"] == "generic":
                pass  # keep bank_statement
            else:
                summary["kind"] = classified["kind"]
            summary.update({k: v for k, v in classified.items() if k not in ("kind",)})
        except Exception as e:
            summary["table_parse_error"] = str(e)

    # Always try to extract a few finance signals from the raw text
    summary["signals"] = _text_signals(text)
    return summary


def _rows_to_df(rows: list[list[str]]) -> pd.DataFrame:
    # Heuristic: first row that has all non-empty distinct strings is the header
    header_idx = 0
    for i, r in enumerate(rows[:5]):
        if all(c for c in r) and len(set(r)) == len(r):
            header_idx = i
            break
    header = rows[header_idx]
    body = rows[header_idx + 1:]
    width = max(len(header), max((len(r) for r in body), default=0))
    header = (header + [f"col_{i}" for i in range(width)])[:width]
    norm = [(r + [""] * width)[:width] for r in body]
    return pd.DataFrame(norm, columns=header)


def _looks_like_bank_statement(text: str) -> bool:
    t = text.lower()
    hits = sum(1 for w in ["statement", "account", "balance", "deposit",
                            "withdrawal", "credit", "debit", "ledger"] if w in t)
    return hits >= 3


_NUMERIC_RE = re.compile(r"^-?\(?\s*[\d,]+(?:\.\d+)?\)?$")


def _to_number(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("EGP", "").replace("$", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if not _NUMERIC_RE.match(s.replace("(", "").replace(")", "")):
        try:
            return float(s)
        except Exception:
            return None
    try:
        return -float(s) if neg else float(s)
    except Exception:
        return None


def _classify_dataframe(df: pd.DataFrame, *, source: str) -> dict:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    cols = {c.lower(): c for c in df.columns}

    def find_col(candidates: list[str]) -> Optional[str]:
        for cand in candidates:
            for k, v in cols.items():
                if cand in k:
                    return v
        return None

    kind = "generic"
    payload: dict[str, Any] = {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "source": source,
    }

    amt_col = find_col(["amount", "balance", "credit", "debit", "paid", "billed"])
    date_col = find_col(["date", "posted", "as of"])
    payer_col = find_col(["payer", "insurer", "company"])
    aging_cols = [c for c in df.columns if re.search(r"0\s*-\s*30|31\s*-\s*60|61\s*-\s*90|>?\s*90|>?\s*180", c.lower())]

    # AR aging
    if aging_cols and (payer_col or "patient" in " ".join(cols.keys())):
        kind = "ar_aging"
        bucket_totals = {}
        for c in aging_cols:
            vals = [_to_number(v) or 0 for v in df[c].tolist()]
            bucket_totals[c] = round(sum(vals), 2)
        total = round(sum(bucket_totals.values()), 2)
        payload.update({
            "kind": kind,
            "aging_buckets": bucket_totals,
            "total_outstanding": total,
            "top_offenders": _top_n_by_total(df, payer_col, aging_cols, n=5) if payer_col else [],
        })
        return payload

    # Bank-like statement (transactions with amount + date)
    if amt_col and date_col:
        kind = "bank_statement"
        amts = [(_to_number(v) or 0) for v in df[amt_col].tolist()]
        credits = [a for a in amts if a > 0]
        debits = [a for a in amts if a < 0]
        payload.update({
            "kind": kind,
            "transaction_count": len(amts),
            "credits": {"count": len(credits), "sum": round(sum(credits), 2),
                          "avg": round(statistics.mean(credits), 2) if credits else 0.0},
            "debits": {"count": len(debits), "sum": round(sum(debits), 2),
                         "avg": round(statistics.mean(debits), 2) if debits else 0.0},
            "net_movement": round(sum(amts), 2),
            "largest_credit": round(max(credits), 2) if credits else 0.0,
            "largest_debit": round(min(debits), 2) if debits else 0.0,
        })
        return payload

    # Payer remit (rows of {payer, billed, paid, denied})
    if payer_col and amt_col:
        kind = "payer_remit"
        # group by payer
        df2 = df.copy()
        df2["_amt"] = [_to_number(v) or 0 for v in df2[amt_col].tolist()]
        grouped = df2.groupby(payer_col)["_amt"].sum().sort_values(ascending=False)
        payload.update({
            "kind": kind,
            "by_payer": [{"payer": str(k), "amount": round(float(v), 2)} for k, v in grouped.items()][:20],
            "total": round(float(df2["_amt"].sum()), 2),
        })
        return payload

    # GL export with revenue/cost columns
    rev_col = find_col(["revenue", "income", "sales"])
    cost_col = find_col(["cost", "expense"])
    if rev_col and cost_col:
        kind = "gl_export"
        rev = [(_to_number(v) or 0) for v in df[rev_col].tolist()]
        cost = [(_to_number(v) or 0) for v in df[cost_col].tolist()]
        payload.update({
            "kind": kind,
            "revenue_total": round(sum(rev), 2),
            "cost_total": round(sum(cost), 2),
            "margin_total": round(sum(rev) - sum(cost), 2),
            "margin_pct": round((sum(rev) - sum(cost)) / sum(rev) * 100, 2) if sum(rev) else 0.0,
        })
        return payload

    # Generic: just return shape + numeric column stats
    num_stats = {}
    for c in df.columns:
        vals = [_to_number(v) for v in df[c].tolist()]
        vals = [v for v in vals if v is not None]
        if len(vals) >= 3:
            num_stats[c] = {
                "n": len(vals),
                "sum": round(sum(vals), 2),
                "mean": round(statistics.mean(vals), 2),
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
            }
    payload.update({"kind": kind, "numeric_columns": num_stats})
    return payload


def _top_n_by_total(df: pd.DataFrame, group_col: str, value_cols: list[str], n: int) -> list[dict]:
    df2 = df.copy()
    df2["_total"] = sum((pd.to_numeric(df2[c].apply(_to_number), errors="coerce").fillna(0)) for c in value_cols)
    grouped = df2.groupby(group_col)["_total"].sum().sort_values(ascending=False).head(n)
    return [{"name": str(k), "total": round(float(v), 2)} for k, v in grouped.items()]


def _text_signals(text: str) -> dict:
    """Pull headline numbers out of a PDF statement's free text."""
    t = text.replace("\u00a0", " ")
    out: dict[str, Any] = {}
    for label, key in [
        (r"(?:opening|beginning)\s+balance", "opening_balance"),
        (r"(?:closing|ending)\s+balance", "closing_balance"),
        (r"total\s+credits?", "total_credits"),
        (r"total\s+debits?", "total_debits"),
        (r"(?:net\s+)?(?:cash\s+)?movement", "net_movement"),
    ]:
        m = re.search(rf"{label}[^0-9\-]*([\-\(]?\s*[\d,]+(?:\.\d+)?\)?)", t, re.I)
        if m:
            v = _to_number(m.group(1))
            if v is not None:
                out[key] = v
    # Date range
    dates = re.findall(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", t)
    if dates:
        out["dates_seen"] = sorted(set(dates))[:6]
    return out
