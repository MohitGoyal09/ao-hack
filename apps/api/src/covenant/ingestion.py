"""Deterministic ingestion of real source documents into covenant cases.

This module reads primary bank paper and SEC filings and compiles the same
typed domain objects the demo catalog uses, so real documents flow through
the identical calculator, policy, and audit path as the hand-typed cases.
Extraction is deterministic text parsing; it never asks a model to invent
rules or figures.

The Aon case uses two sources:

* ``data/raw/pdf-fixtures/aon-credit-agreement.pdf`` - Aon North America,
  Inc. Term Loan Credit Agreement dated February 16, 2024 (SEC exhibit 10.2
  to the Aon plc 8-K).  Supplies the financial covenant (Section 6.14) and
  its definitions (Section 1.01).
* ``data/raw/sec/aon/2023-form-10k.html`` - Aon plc 2023 Form 10-K.  Supplies
  the fiscal-2023 financial figures and the debt note.

The extraction results are cached per process so PDF page parsing is paid
once no matter how many times the catalog is rebuilt.
"""

from __future__ import annotations

import functools
import hashlib
import html
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pdfplumber

from .domain import (
    Citation,
    CovenantCase,
    CovenantRule,
    DocumentVersion,
    FinancialFact,
)
from .hashing import stable_hash

AON_CASE_ID = "aon-term-loan-leverage"
AON_DOCUMENT_ID = "aon-2024-term-loan-agreement"
AON_CLOSING_DATE = "2024-02-16"
AON_TEST_DATE = "2024-03-31"
AON_FINANCIAL_PERIOD = "Fiscal year ended 2023-12-31"
AON_DOCUMENT_TITLE = "Aon North America, Inc. Term Loan Credit Agreement"
AON_10K_TITLE = "Aon plc 2023 Form 10-K"
AON_LEVERAGE_SECTION = "6.14(b)"

# PDF page index shifts by one: the first PDF page is the SEC cover page.
_COVER_PAGE_OFFSET = 1

_COVENANT_MARKER = re.compile(r"\( ?b ?\)\s*Consolidated Leverage Ratio")
_THRESHOLD_PATTERN = re.compile(r"not more than ([\d.]+):1\.00")
_DEFINITION_MARKER = re.compile(
    r"\u201c\s*Consolidated Leverage Ratio\s*\u201d\s*means,"
    r"\s*as of the last day of any Measurement Period"
)
_TOTAL_DEBT = re.compile(r"Unamortized discounts[^$]{0,140}\$\s*([\d,]+)")
_NET_INCOME = re.compile(r"Net income\s+([\d,]+)")
_INCOME_TAX = re.compile(r"Income tax expense\s+([\d,]+)")
_INTEREST_EXPENSE = re.compile(r"Interest expense\s+\(?([\d,]+)\)?")
_DEPRECIATION = re.compile(r"Depreciation of fixed assets\s+([\d,]+)")
_AMORTIZATION = re.compile(r"Amortization and impairment of intangible assets\s+([\d,]+)")


def data_root() -> Path:
    """Repository ``data/raw`` directory, overridable via ``COVENANT_DATA_ROOT``."""
    override = os.environ.get("COVENANT_DATA_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[4] / "data" / "raw"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _html_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return _collapse(html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def _excerpt(text: str, start: int, length: int = 360) -> str:
    window = text[start : start + length].strip()
    if len(text) > start + length:
        window = window.rsplit(" ", 1)[0] + " …"
    return window


@dataclass(frozen=True)
class LeverageTier:
    """One step of the Section 6.14(b) threshold schedule."""

    step: str
    threshold: float


@dataclass(frozen=True)
class ExtractedAonRule:
    """Typed extraction of the Aon leverage covenant from the credit agreement PDF."""

    name: str
    formula_label: str
    comparator: str
    tiers: tuple[LeverageTier, ...]
    section: str
    section_page: int
    section_excerpt: str
    definition_page: int
    definition_excerpt: str
    document_id: str
    document_title: str
    effective_date: str
    document_hash: str


@dataclass(frozen=True)
class ExtractedFinancialFact:
    """One typed financial input extracted from the 10-K."""

    key: str
    label: str
    amount: float
    locator: str


@functools.cache
def _pdf_page_texts(pdf_path: Path) -> tuple[str, ...]:
    with pdfplumber.open(pdf_path) as pdf:
        return tuple(_collapse(page.extract_text() or "") for page in pdf.pages)


def extract_aon_rule(pdf_path: Path | None = None) -> ExtractedAonRule:
    """Parse the credit-agreement PDF for Section 6.14(b) and Section 1.01."""
    path = pdf_path or data_root() / "pdf-fixtures" / "aon-credit-agreement.pdf"
    if not path.is_file():
        raise FileNotFoundError(f"Aon credit agreement PDF not found at {path}")
    pages = _pdf_page_texts(path)
    document_hash = _sha256(path)

    covenant_pages = [index for index, text in enumerate(pages) if _COVENANT_MARKER.search(text)]
    if not covenant_pages:
        raise ValueError(
            "Could not locate the Section 6.14(b) Consolidated Leverage Ratio "
            f"covenant in {path.name}."
        )
    section_index = covenant_pages[0]
    section_text = pages[section_index]

    thresholds = [float(value) for value in _THRESHOLD_PATTERN.findall(section_text)]
    if len(thresholds) != 3:
        raise ValueError(
            "Expected the three Section 6.14(b) thresholds (4.00, 3.75, 3.25); "
            f"found {thresholds!r}."
        )
    steps = (
        "(i) first and second consecutive full fiscal quarters ending after the Closing Date",
        "(ii) third, fourth and fifth consecutive full fiscal quarters ending after the Closing Date",
        "(iii) sixth and each later consecutive full fiscal quarter ending after the Closing Date",
    )
    tiers = tuple(LeverageTier(step, threshold) for step, threshold in zip(steps, thresholds))

    definition_pages = [
        index for index, text in enumerate(pages) if _DEFINITION_MARKER.search(text)
    ]
    if not definition_pages:
        raise ValueError(
            "Could not locate the Section 1.01 'Consolidated Leverage Ratio' "
            f"definition in {path.name}."
        )
    definition_index = definition_pages[0]
    definition_match = _DEFINITION_MARKER.search(pages[definition_index])

    return ExtractedAonRule(
        name="Maximum Consolidated Leverage Ratio",
        formula_label=(
            "Consolidated Funded Debt ÷ Consolidated Adjusted EBITDA"
        ),
        comparator="<=",
        tiers=tiers,
        section=AON_LEVERAGE_SECTION,
        section_page=section_index + _COVER_PAGE_OFFSET,
        section_excerpt=_excerpt(section_text, _COVENANT_MARKER.search(section_text).start()),
        definition_page=definition_index + _COVER_PAGE_OFFSET,
        definition_excerpt=_excerpt(pages[definition_index], definition_match.start()),
        document_id=AON_DOCUMENT_ID,
        document_title=AON_DOCUMENT_TITLE,
        effective_date=AON_CLOSING_DATE,
        document_hash=document_hash,
    )


@functools.cache
def extract_aon_financials(tenk_path: Path | None = None) -> tuple[ExtractedFinancialFact, ...]:
    """Parse the 10-K for the fiscal-2023 lines used by the leverage covenant."""
    path = tenk_path or data_root() / "sec" / "aon" / "2023-form-10k.html"
    if not path.is_file():
        raise FileNotFoundError(f"Aon 2023 Form 10-K not found at {path}")
    text = _html_text(path)

    def amount(pattern: re.Pattern[str]) -> float:
        match = pattern.search(text)
        if match is None:
            raise ValueError(
                f"Could not extract '{pattern.pattern}' from {path.name}."
            )
        return float(match.group(1).replace(",", ""))

    net_income = amount(_NET_INCOME)
    income_tax = amount(_INCOME_TAX)
    interest_expense = amount(_INTEREST_EXPENSE)
    depreciation = amount(_DEPRECIATION)
    amortization = amount(_AMORTIZATION)
    funded_debt = amount(_TOTAL_DEBT)

    ebitda = net_income + income_tax + interest_expense + depreciation + amortization

    income_statement = "Consolidated Statements of Income"
    facts = (
        ExtractedFinancialFact(
            key="funded_debt",
            label="Total debt (proxy for Consolidated Funded Debt)",
            amount=funded_debt,
            locator="Note 15 — Debt: Total debt at December 31, 2023, after "
            "unamortized discounts, premiums and debt issuance costs",
        ),
        ExtractedFinancialFact(
            key="net_income",
            label="Net income",
            amount=net_income,
            locator=f"{income_statement} — Net income",
        ),
        ExtractedFinancialFact(
            key="income_tax",
            label="Income tax expense",
            amount=income_tax,
            locator=f"{income_statement} — Income tax expense",
        ),
        ExtractedFinancialFact(
            key="interest_expense",
            label="Interest expense",
            amount=interest_expense,
            locator=f"{income_statement} — Interest expense",
        ),
        ExtractedFinancialFact(
            key="depreciation",
            label="Depreciation of fixed assets",
            amount=depreciation,
            locator=f"{income_statement} — Depreciation of fixed assets",
        ),
        ExtractedFinancialFact(
            key="amortization",
            label="Amortization and impairment of intangible assets",
            amount=amortization,
            locator=f"{income_statement} — Amortization and impairment of intangible assets",
        ),
        ExtractedFinancialFact(
            key="ebitda",
            label=(
                "EBITDA (proxy for Consolidated Adjusted EBITDA; computed as net income "
                "+ income tax + interest expense + depreciation + amortization)"
            ),
            amount=ebitda,
            locator=(
                f"Computed from {income_statement} line items: "
                f"net income {net_income:,.0f} + income tax {income_tax:,.0f} + "
                f"interest expense {interest_expense:,.0f} + depreciation {depreciation:,.0f} "
                f"+ amortization and impairment {amortization:,.0f}"
            ),
        ),
    )
    return facts


def _next_quarter_end(reference: date) -> date:
    for year in range(reference.year, reference.year + 3):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            candidate = date(year, month, day)
            if candidate > reference:
                return candidate
    raise ValueError(f"Could not find a fiscal quarter end after {reference}")


def _quarter_index(test_date: date, closing_date: date) -> int:
    """1-based index of the fiscal quarter whose measurement end equals *test_date*."""
    end = _next_quarter_end(closing_date)
    index = 1
    while end < test_date:
        end = _next_quarter_end(end)
        index += 1
    if end != test_date:
        raise ValueError(
            f"Test date {test_date.isoformat()} is not a fiscal quarter end "
            f"after the Closing Date {closing_date.isoformat()}."
        )
    return index


def _tier_for_quarter(tiers: tuple[LeverageTier, ...], quarter_index: int) -> LeverageTier:
    if quarter_index <= 2:
        return tiers[0]
    if quarter_index <= 5:
        return tiers[1]
    return tiers[2]


def select_aon_leverage_threshold(test_date: str | None = None) -> tuple[float, str]:
    """Select the Section 6.14(b) threshold that applies to *test_date*.

    Returns ``(threshold, reason)`` where *reason* records which step of the
    schedule was selected and why.
    """
    tiers = extract_aon_rule().tiers
    test = date.fromisoformat(test_date or AON_TEST_DATE)
    closing = date.fromisoformat(AON_CLOSING_DATE)
    index = _quarter_index(test, closing)
    tier = _tier_for_quarter(tiers, index)
    reason = (
        f"Section 6.14(b): {tier.step}; "
        f"fiscal quarter #{index} ending {test_date or AON_TEST_DATE} after the "
        f"{AON_CLOSING_DATE} Closing Date caps the ratio at {tier.threshold:.2f}:1.00."
    )
    return tier.threshold, reason


def build_aon_term_loan_case(raw_dir: Path | None = None) -> CovenantCase:
    """Compile the Aon term-loan leverage case from the real source documents."""
    base = raw_dir or data_root()
    rule = extract_aon_rule(base / "pdf-fixtures" / "aon-credit-agreement.pdf")
    tenk_path = base / "sec" / "aon" / "2023-form-10k.html"
    extracted_facts = extract_aon_financials(tenk_path)
    tenk_hash = _sha256(tenk_path)

    fact_map = {fact.key: fact for fact in extracted_facts}
    funded_debt = fact_map["funded_debt"]
    ebitda = fact_map["ebitda"]

    threshold, threshold_reason = select_aon_leverage_threshold()

    def financial_fact(extracted: ExtractedFinancialFact) -> FinancialFact:
        return FinancialFact(
            key=extracted.key,
            label=extracted.label,
            amount=extracted.amount,
            period=AON_FINANCIAL_PERIOD,
            source=f"{AON_10K_TITLE} (fiscal year ended 2023-12-31)",
            source_locator=extracted.locator,
            source_hash=stable_hash(
                {
                    "source": AON_10K_TITLE,
                    "locator": extracted.locator,
                    "amount": extracted.amount,
                    "period": AON_FINANCIAL_PERIOD,
                    "source_sha256": tenk_hash,
                }
            ),
            supported=True,
        )

    citation_hash = stable_hash(
        {
            "id": rule.document_id,
            "title": rule.document_title,
            "section": rule.section,
            "sha256": rule.document_hash,
        }
    )
    citations = [
        Citation(
            document_id=rule.document_id,
            document=rule.document_title,
            locator=f"§{rule.section}, PDF p. {rule.section_page}",
            excerpt=rule.section_excerpt,
            document_hash=citation_hash,
        ),
        Citation(
            document_id=rule.document_id,
            document=rule.document_title,
            locator=f"§1.01, PDF p. {rule.definition_page}",
            excerpt=rule.definition_excerpt,
            document_hash=citation_hash,
        ),
    ]

    narrative = (
        "Real SEC-filed source, not hand-typed. The Maximum Consolidated Leverage "
        "Ratio covenant (Section 6.14(b)) and its Section 1.01 definitions were "
        "extracted from the Aon North America, Inc. Term Loan Credit Agreement "
        "dated February 16, 2024 (SEC exhibit 10.2). Financial inputs were "
        "extracted from the Aon plc 2023 Form 10-K. The available fiscal-2023 "
        "financials precede the first measurement period under the agreement "
        "(fiscal quarter ending 2024-03-31), and the financial inputs are "
        "line-item proxies for the contract-defined terms. This case therefore "
        f"demonstrates real extraction and deterministic arithmetic on real bank "
        f"paper, not a certification verdict for Aon. {threshold_reason}"
    )

    return CovenantCase(
        id=AON_CASE_ID,
        name="Aon: term loan leverage from SEC-filed source",
        narrative=narrative,
        agreement=rule.document_title,
        agreement_version="Original agreement dated 2024-02-16",
        test_date=AON_TEST_DATE,
        scenario_type="comparison",
        documents=[
            DocumentVersion(
                id=rule.document_id,
                title=rule.document_title,
                kind="agreement",
                effective_date=rule.effective_date,
                controlling=True,
            )
        ],
        rule=CovenantRule(
            id="aon-max-consolidated-leverage",
            name=rule.name,
            formula_label=rule.formula_label,
            numerator_keys=["funded_debt"],
            subtract_keys=[],
            denominator_keys=["ebitda"],
            threshold=threshold,
            comparator=rule.comparator,
            measurement_period=AON_FINANCIAL_PERIOD,
            citations=citations,
            active=True,
        ),
        facts=[financial_fact(extracted) for extracted in extracted_facts],
        unsupported_obligations=[
            "Interest coverage ratio — out of scope for v1; "
            "detected but not calculated.",
        ],
        risk_note=(
            "Period mismatch: the fiscal-2023 financials antedate the first "
            "Q1-2024 measurement period, and the 10-K total-debt line proxies "
            "Consolidated Funded Debt while computed EBITDA proxies the "
            "contract-defined Consolidated Adjusted EBITDA (which permits "
            "specified add-backs). On these proxies the ratio is far below the "
            f"{threshold:.2f}x Q1-2024 cap, but no lender-ready conclusion is "
            "implied."
        ),
    )