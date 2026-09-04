# Covenant Certificate: Domain and Build Research

Date: 2026-09-04

Status: research decision for Syndicate by Maximor, Track 2

## 1. The idea in simple language

A company borrows money under a loan agreement. The agreement contains financial promises called covenants. Examples include:

- Debt must stay below 4.0 times EBITDA.
- Interest coverage must stay above 2.5 times.
- Cash must not fall below $10 million.

The difficult part is that the agreement defines words such as "Debt" and "EBITDA" in its own way. Two lenders can use different definitions for the same company. The same financial statements can therefore pass one agreement and fail another.

Covenant Certificate reads the loan agreement and the latest financial data. It finds the applicable covenant, follows its definitions and cross-references, calculates the result using deterministic code, and shows the exact clauses and financial lines used. It drafts the compliance certificate for an authorized finance officer to review and sign. If evidence is missing or a clause is unclear, it refuses to certify and requests review.

The product does not replace legal, accounting, lender, or officer judgment. It prepares a traceable draft and routes uncertain cases to the appropriate reviewer.

## 2. Track and product boundary

This is a Track 2, Autonomous Office of the CFO project. It belongs to treasury, controllership, lender reporting, and financial compliance.

AO is used to build the project. AO is not required in the product runtime.

The product should be a focused covenant workflow. It should not be presented as a general document-agent harness. Reusable extraction, evidence, calculation, and review components can exist internally.

## 3. The real business workflow

The precise process varies by agreement, but a defensible borrower-side workflow is:

1. Register the facility, current agreement, amendments, waivers, reporting calendar, and required certificate form.
2. Determine the test date, measurement period, borrower group, and covenants that are active for that period.
3. Resolve the controlling document version. Later amendments and waivers may replace terms in the original agreement.
4. Extract each applicable covenant and its complete definition chain.
5. Collect the financial package. This can include financial statements, trial balance, debt schedule, lease schedule, cash balances, acquisition or disposition schedules, and evidence for requested EBITDA adjustments.
6. Map accounting lines to agreement-defined inputs.
7. Calculate every ratio and amount with deterministic code.
8. Compare actual results with the applicable threshold and calculate headroom.
9. Route missing evidence, ambiguous terms, unusual adjustments, potential breaches, and low-headroom results to a reviewer.
10. Populate the agreement-specific form of compliance certificate and its calculation schedules.
11. Obtain approval and signature from the officer specified by the agreement.
12. Deliver the signed certificate by the contract deadline and preserve the source package, calculations, approvals, and document versions.

Many public credit agreements define "Compliance Certificate" by reference to a named exhibit. A public Aon agreement, for example, identifies an "Exhibit B Form of Compliance Certificate" and separately defines its leverage ratio and debt components. This supports using the agreement's own certificate form instead of a generic template. [Public agreement text](https://github.com/nlmatics/nlm-ingestor/blob/main/files/text/credit_aon_baseline.txt)

## 4. Domain concepts the system must represent

### 4.1 Covenant classes

The first product version should support financial maintenance covenants only. Common examples are:

- Maximum gross or net leverage ratio
- Maximum first-lien or secured leverage ratio
- Minimum interest coverage ratio
- Minimum fixed-charge coverage ratio
- Minimum debt-service coverage ratio, especially in project finance
- Minimum liquidity
- Minimum tangible net worth

Do not mix these with every other promise in a credit agreement:

- Affirmative covenants require actions such as delivering statements or maintaining insurance.
- Negative covenants restrict actions such as taking new debt, granting liens, making acquisitions, or paying dividends.
- Incurrence covenants are tested when a specified action occurs.
- Maintenance covenants are tested periodically even when no transaction occurs.
- A springing covenant becomes active only when its contractual trigger is met, such as revolver usage exceeding a stated level.

The first release should calculate periodic maintenance covenants and flag other covenant types as outside scope.

### 4.2 The formula is contract-specific

The product must not use one generic finance formula. It must compile the agreement's definitions.

Examples:

```text
Gross leverage = agreement-defined funded debt / agreement-defined EBITDA
Net leverage   = (agreement-defined debt - permitted cash) / agreement-defined EBITDA
Interest cover = agreement-defined EBITDA / agreement-defined interest
DSCR           = agreement-defined cash flow available for debt service / agreement-defined debt service
```

Each term can contain important modifications:

- Whether operating or finance leases count as debt
- Whether guarantees, letters of credit, earn-outs, or seller notes count
- Whether cash can be deducted, which cash qualifies, and whether a cap applies
- Which subsidiaries are included or excluded
- Currency conversion rules
- Permitted EBITDA add-backs and caps
- Pro forma treatment for acquisitions and disposals
- Cost savings or synergies that may be added back
- One-time, restructuring, stock-compensation, litigation, or transaction costs
- Whether interest means total interest expense or cash interest
- Trailing-twelve-month, quarterly, annual, or forward-looking measurement periods

The Aon public agreement illustrates this problem: its funded-debt definition excludes specified operating leases and permits limited treatment of hybrid securities before its leverage ratio is calculated. The displayed financial statement line alone is therefore not the contractual input. [Public agreement text](https://github.com/nlmatics/nlm-ingestor/blob/main/files/text/credit_aon_baseline.txt)

### 4.3 Threshold schedules and applicability

A covenant may not have one permanent threshold. The system must handle:

- Step-down or step-up schedules by quarter or date
- Temporary increases after a qualifying acquisition
- Springing activation conditions
- Different thresholds for different facilities
- Waivers for one test period
- Amendments effective on a specified date
- Grace or cure periods

Every result must state why a threshold applies to the selected test date.

### 4.4 Document precedence and version control

This is a core risk, not an optional feature. The system needs a document set rather than one PDF:

```text
Original credit agreement
  -> amendment 1
  -> amendment 2
  -> current waiver or consent
  -> current certificate form
```

The output must name the controlling version for each extracted term. If two active documents conflict and precedence cannot be proved, the result must be `NEEDS_REVIEW`.

### 4.5 Roles and legal boundary

The borrower typically prepares and delivers the certificate. An authorized officer signs it under the agreement. The administrative agent or lenders may review it and may independently challenge the calculation.

The software should use these labels:

- `DRAFT_COMPLIANT`
- `DRAFT_BREACH`
- `NEEDS_REVIEW`

It should not claim that the AI legally "certified" compliance. The final certificate remains subject to authorized human review and signature.

## 5. Required inputs

### Contract package

- Executed credit or facility agreement
- All amendments, restatements, waivers, and consents
- Agreement-specific form of compliance certificate
- Reporting calendar and facility metadata

### Financial package

- Balance sheet and income statement
- Trial balance or normalized ledger export where available
- Debt schedule, including current and long-term portions
- Cash and restricted-cash schedule
- Lease schedule
- Interest schedule
- Acquisition, disposition, restructuring, and synergy schedules
- Management evidence for proposed EBITDA adjustments
- Prior approved certificate and calculation workbook

### Human context

- Reviewer identity and authority
- Prior approved interpretations
- Policies for materiality and review
- Current lender correspondence concerning waivers or amendments

## 6. Proposed structured rule model

Each covenant should compile into a versioned object similar to:

```json
{
  "covenant_id": "max_total_net_leverage",
  "agreement_version": "amendment-2",
  "test_date": "2026-06-30",
  "active": true,
  "activation_condition": null,
  "numerator": {
    "concept": "Consolidated Total Net Debt",
    "components": [],
    "adjustments": [],
    "source_clauses": []
  },
  "denominator": {
    "concept": "Consolidated Adjusted EBITDA",
    "components": [],
    "adjustments": [],
    "caps": [],
    "source_clauses": []
  },
  "operator": "<=",
  "threshold": 4.0,
  "measurement_period": "trailing_twelve_months",
  "threshold_source": {},
  "certificate_template_source": {}
}
```

Every extracted field needs a document ID, page or section locator, exact supporting span, parser version, model version, and confidence or review status.

## 7. Calculation and decision rules

The language model may extract candidate rules and map candidate financial facts. It must not perform the final arithmetic or silently decide legal applicability.

Use deterministic code for:

- Addition, subtraction, multiplication, division, minimum, and maximum
- Currency and unit normalization
- Period aggregation
- Threshold comparison
- Headroom calculation
- Adjustment-cap enforcement
- Completeness checks

Do not execute model-generated Python or use unrestricted `eval`. Compile only to a small allow-listed expression language or typed operation tree.

Suggested status policy:

```text
NEEDS_REVIEW if:
  controlling document is unresolved
  OR an active covenant may have been missed
  OR a required definition is unresolved
  OR any source figure lacks evidence
  OR an adjustment lacks support
  OR units or periods do not reconcile
  OR extraction confidence is below policy

DRAFT_BREACH if:
  evidence is complete
  AND deterministic calculation fails the threshold

DRAFT_COMPLIANT if:
  evidence is complete
  AND all applicable covenants pass
```

Near-limit cases should be highlighted by absolute and percentage headroom. The agreement, not a generic 20% rule, controls whether a legal breach exists.

## 8. Failure modes that matter

The evaluation set must deliberately contain these cases:

1. A definition that points through several other defined terms.
2. An amendment that changes only one ratio threshold.
3. A waiver that applies to one quarter only.
4. A step-down schedule where the test date selects a different threshold.
5. A springing covenant whose activation trigger is not met.
6. Gross debt versus net debt.
7. Restricted cash that cannot be netted.
8. Operating leases included in one agreement and excluded in another.
9. An EBITDA add-back subject to a cap.
10. Acquisition pro forma adjustments.
11. Conflicting periods, currencies, or units.
12. Missing support for a management adjustment.
13. A scanned page with OCR damage to a decimal or inequality.
14. A covenant disclosed in the agreement but absent from the generated rule set.
15. A certificate deadline or signatory requirement that is missed.

The most dangerous error is a false compliant result. The product should prefer review over unsupported compliance.

## 9. Evaluation design

### Gold set

Create a small expert-reviewed dataset from public SEC-filed credit agreements and related financial statements. Split by agreement, not by page or text chunk, so similar pages from one agreement cannot appear in both training and test sets.

For each case, the gold record should include:

- Applicable agreement version
- Active covenant set
- Formula and complete definition chain
- Applicable threshold and test period
- Each financial input and source
- Permitted and rejected adjustments
- Expected arithmetic
- Expected draft status
- Required certificate fields
- Known ambiguity and expected abstention

### Metrics

Use code-based measures where possible:

| Metric | Meaning | Target for demo |
|---|---|---:|
| Covenant recall | Active covenants found | 100% on curated set |
| Rule-field exactness | Operator, threshold, period, schedule | >=95% |
| Citation validity | Citation supports extracted field | 100% reviewed sample |
| Calculation accuracy | Deterministic result equals gold | 100% |
| Draft-status accuracy | Correct compliant, breach, or review state | >=95% |
| Unsupported compliant rate | Compliant without complete evidence | 0% |
| Amendment precedence | Correct current term selected | 100% on amendment cases |
| Certificate completeness | Required fields populated or flagged | 100% |

Do not use an LLM judge to grade arithmetic. Expert review is still required for contract interpretation and evidence sufficiency.

### Strong demonstration set

Use three visibly different cases:

1. Same financials, agreement A passes and agreement B breaches because Debt or EBITDA is defined differently.
2. Original agreement breaches, but a current amendment changes the applicable threshold. The system identifies the controlling version.
3. Missing add-back evidence causes `NEEDS_REVIEW`. After a reviewer accepts or rejects the adjustment, the calculation and draft certificate update with an audit trail.

## 10. Recommended product architecture

```text
Document intake
  -> parser with page and section anchors
  -> section and defined-term locator
  -> cross-reference and amendment graph
  -> typed covenant-rule extraction
  -> rule completeness review

Financial intake
  -> table and spreadsheet parser
  -> normalized fact ledger
  -> contract-specific fact mapping
  -> adjustment evidence checks

Rule + facts
  -> safe deterministic calculator
  -> threshold and headroom evaluator
  -> review-policy gate
  -> agreement-specific certificate renderer
  -> approval and audit log
```

This is a bounded workflow, not an open-ended multi-agent system. A single orchestrator can call specialist extraction and validation steps. State transitions and approvals should be explicit.

## 11. Open-source research

### 11.1 Directly overlapping projects

#### Solveo

[Potti1234/Solveo](https://github.com/Potti1234/Solveo) is an MIT-licensed, full-stack SEC filing and covenant-risk workspace. It resolves SEC tickers, discovers Exhibit 10.1 documents, extracts covenant rules and financial lines, runs calculations, and produces an evidence and calculation trail.

Assessment:

- It proves that public SEC data and Exhibit 10.1 discovery are viable.
- It is very close to the proposed project, so the claim that nobody has built this is false.
- It has one GitHub star and only one visible audit test script in the repository tree at the time of review.
- It depends heavily on Vultr inference and retrieval services.
- Its own README states that PDF upload is not its primary path.
- Its implementation contains useful SEC discovery and evidence-trail patterns.

Decision: do not fork Solveo as the hackathon base. A fork would weaken originality and inherit provider coupling. Study its SEC URL construction, filing-document discovery, and explainability schema. Reimplement only the small generic pieces needed, with attribution if code is copied.

Our required differentiation:

- Agreement-specific compliance certificate generation
- Full definition cross-reference graph
- Amendment and waiver precedence
- Same-financials, different-agreement comparison
- Explicit safe-abstention policy
- Authorized officer review and signature boundary
- Gold evaluation for missed covenants and false compliance

#### Knowledge Stack loan covenant monitor

[knowledgestack/ks-cookbook](https://github.com/knowledgestack/ks-cookbook/tree/main/flagships/loan_covenant_monitor) contains an MIT-licensed covenant monitor built with LangGraph, MCP retrieval, and structured citations.

Assessment:

- The schema and report sections are useful references.
- It requires the proprietary Knowledge Stack service and API key.
- The repository's own README marks the last verification as `EMPTY_OUTPUT` because required grounding markers were not found.
- Its prompt assumes a fixed list of covenant types and a generic 20% warning rule. Those assumptions are unsafe as a general contract interpretation policy.

Decision: use it as a checklist only. Do not use it as the application base.

### 11.2 Recommended reusable components

#### Docling

[docling-project/docling](https://github.com/docling-project/docling) is MIT licensed and supports PDF, DOCX, XLSX, HTML, OCR, tables, formulas, local execution, and structured document output.

Decision: recommended for primary document parsing. Preserve page, table, heading, and bounding-box provenance in our own data model.

#### sec-downloader

[Elijas/sec-downloader](https://github.com/Elijas/sec-downloader) is MIT licensed and retrieves SEC filings while supporting the SEC's declared user-agent requirement.

Decision: recommended for assembling public demo agreements and filings. Cache results and follow SEC fair-access limits.

#### CUAD

[The Atticus Project CUAD](https://github.com/The-Atticus-Project/cuad) provides expert-annotated legal contract review data and baseline models.

Decision: useful for evidence-extraction ideas, not as the covenant gold set. Its contract categories do not provide agreement-specific covenant calculations. Verify dataset redistribution terms before packaging any records.

#### ContractNLI

[stanfordnlp/contract-nli](https://github.com/stanfordnlp/contract-nli) is a CC BY 4.0 dataset for contract-level entailment, contradiction, and evidence identification.

Decision: useful for testing evidence grounding and abstention patterns. It concerns NDA clauses rather than credit covenants, so it cannot validate domain accuracy.

#### FinQA

[czyssrs/FinQA](https://github.com/czyssrs/FinQA) is an MIT-licensed numerical-reasoning dataset with gold programs and execution answers.

Decision: reuse its program-and-execution evaluation pattern, not its trained model or data as covenant ground truth.

#### Unstructured

[Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured) is an Apache 2.0 document ETL library.

Decision: valid fallback if Docling fails on specific formats. Do not add both to the first implementation without a measured parsing need.

#### sec-parser

[alphanome-ai/sec-parser](https://github.com/alphanome-ai/sec-parser) is MIT licensed but now labels itself unmaintained.

Decision: do not choose it as the main dependency. Its semantic-tree design remains a useful reference.

## 12. Fast-track build decision

Do not build a general harness and do not fork an existing covenant application.

Use this focused stack:

| Need | Recommended choice |
|---|---|
| PDF, DOCX, XLSX, OCR parsing | Docling |
| Public SEC document acquisition | sec-downloader plus SEC submissions data |
| Typed extraction outputs | Pydantic models and provider-supported structured output |
| Workflow API | FastAPI |
| State and audit trail | Supabase Postgres from the first environment |
| Safe calculations | Small typed expression tree evaluated by local code |
| Source and generated files | Private Supabase Storage buckets |
| Certificate rendering | Agreement template mapping plus DOCX or HTML-to-PDF renderer |
| Review UI | Focused web interface showing clause, source fact, calculation, status, and approval |
| Evaluation | Pytest fixtures plus a versioned gold JSON dataset |

LangGraph is optional. Use it only if its checkpoint and human-review state save more work than a small explicit state machine. A general agent framework is not required for the core product.

## 13. What can be reused safely

Reuse or adapt:

- Docling's document and table parsing
- sec-downloader's SEC acquisition flow
- Pydantic structured schemas
- The filing discovery pattern from Solveo
- Evidence and calculation trail concepts from Solveo
- The report field checklist from Knowledge Stack
- FinQA's separation of predicted program and executed answer
- ContractNLI's evidence-supported or not-mentioned evaluation pattern

Build ourselves:

- Covenant and defined-term schema
- Cross-reference resolver
- Amendment and waiver precedence
- Financial fact mapping
- Safe formula compiler and evaluator
- Completeness and abstention policy
- Agreement-specific certificate generator
- Human approval and decision history
- Covenant-specific gold dataset

## 14. Accuracy controls

1. Every rule, input, adjustment, and threshold must cite source evidence.
2. The system must show the entire definition chain, not only the final covenant paragraph.
3. The model proposes mappings; deterministic code performs calculations.
4. No unsupported value may default to zero.
5. Missing data produces `NEEDS_REVIEW`, never an assumed pass.
6. Amendments and waivers must be resolved before calculation.
7. Scanned decimals, inequalities, and table cells require visual or second-parser confirmation.
8. Agreement-level train and test separation prevents text leakage.
9. A finance or legal expert must review the gold labels.
10. The final output is a draft for officer approval, not legal certification by software.

## 15. Research conclusion

Covenant Certificate remains a strong Track 2 idea, but it is not an untouched category. Two public GitHub projects already cover covenant monitoring or analysis. The winning product must go beyond retrieval and a ratio dashboard.

The defensible wedge is:

> Compile an agreement and its amendments into an evidence-backed covenant policy, apply it to company financials with deterministic calculations, and prepare the agreement-specific certificate while refusing unsupported compliance.

The best fast-track route is a new focused application built from generic open-source components. Do not fork Solveo or the Knowledge Stack monitor as the whole product. Their existence should guide the architecture and sharpen the differentiation.

## 16. Sources reviewed

- [Maximor: What we mean by autonomous finance](https://www.maximor.ai/blog/what-we-mean-by-autonomous-finance)
- [Maximor revenue automation](https://www.maximor.ai/revenue-automation)
- [Maximor automated close](https://www.maximor.ai/automated-close)
- [Public Aon credit agreement text](https://github.com/nlmatics/nlm-ingestor/blob/main/files/text/credit_aon_baseline.txt)
- [Solveo](https://github.com/Potti1234/Solveo)
- [Knowledge Stack covenant monitor](https://github.com/knowledgestack/ks-cookbook/tree/main/flagships/loan_covenant_monitor)
- [Docling](https://github.com/docling-project/docling)
- [sec-downloader](https://github.com/Elijas/sec-downloader)
- [CUAD](https://github.com/The-Atticus-Project/cuad)
- [ContractNLI](https://github.com/stanfordnlp/contract-nli)
- [FinQA](https://github.com/czyssrs/FinQA)
- [Unstructured](https://github.com/Unstructured-IO/unstructured)
- [sec-parser](https://github.com/alphanome-ai/sec-parser)

## 17. Validation still required before implementation

- Obtain several public agreements with certificate exhibits and amendments.
- Ask a qualified finance or legal reviewer to label at least the demonstration cases.
- Confirm the hackathon's rules for pre-existing open-source code and attribution.
- Confirm whether the submission can use public SEC agreements and derived evaluation records.
- Test Docling on the selected agreements, especially cross-references, tables, and scanned exhibits.
