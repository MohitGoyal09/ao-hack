# Covenant Certificate: Primary-source controls brief

**Purpose.** These are product-design findings, not legal or accounting advice. A
covenant result is controlled by the executed agreement, its effective amendments
and waivers, and the agreement-specific certificate form—not by a generic ratio
definition or this application.

## 1. Contract-defined arithmetic is the product boundary

There is no universal DSCR or leverage calculation. For example, one SEC-filed
agreement defines DSCR as trailing-four-quarter EBITDA divided by interest expense
plus *Phantom Amortization*, and requires a minimum that steps from 2.00x to 2.50x.
[SEC-filed credit-agreement amendment (definition and thresholds)](https://www.sec.gov/Archives/edgar/data/16099/000119312511236745/dex101.htm).
Another SEC-filed certificate schedule calculates DSCR from EBITDA less maintenance
capital expenditures, divided by 10% of funded principal plus trailing-12-month cash
interest, with a 1.25x minimum. [SEC-filed agreement, Exhibit C/Schedule A](https://www.sec.gov/Archives/edgar/data/1408356/000119312512416770/d229977dex1010.htm).
The same divergence appears in current issuer disclosure: one issuer calls DSCR
“Covenant EBITDA / Debt Service,” where debt service includes interest and principal
amortization. [SEC-filed issuer definition and reconciliation](https://www.sec.gov/Archives/edgar/data/1995807/000119312525287019/d873314d8k.htm).

Leverage is equally agreement-specific. A filed amendment uses gross *Total
Indebtedness / EBITDA* over four fiscal quarters. [SEC-filed total-leverage definition](https://www.sec.gov/Archives/edgar/data/1517175/000138713115000120/ex10-3.htm).
By contrast, a filed agreement defines consolidated total **net** leverage as
consolidated indebtedness less unrestricted cash, divided by four-quarter consolidated
EBITDA, and permits pro-forma adjustments. [SEC-filed net-leverage definition](https://www.sec.gov/Archives/edgar/data/879526/000119312521293275/d225919dex41.htm).
Another filed disclosure permits specified cash netting and EBITDA add-backs for
non-recurring costs, acquisition costs, restructuring costs, and capped cost savings.
[SEC-filed Revised Credit Agreement summary](https://www.sec.gov/Archives/edgar/data/313143/000095010324006128/dp210533_8k.htm).

**Implementation implication:** store a typed, versioned rule for every agreement:
test date, borrower group, measurement period, numerator and denominator components,
allowed adjustments and caps, inequality, threshold schedule, activation conditions,
and document/section citations. A rule engine must never substitute a canonical
`DSCR` or `net_leverage` formula.

## 2. The certificate must be an evidence bundle, not a conclusion

Public agreements show the expected artefact: a named compliance-certificate exhibit,
delivery alongside financial statements, a responsible officer's certification, and a
schedule containing each calculation line and an explicit `is/is not in compliance`
statement. [SEC-filed agreement: certificate delivery and updates](https://www.sec.gov/Archives/edgar/data/1408356/000119312512416770/d229977dex1010.htm) · [same agreement: Exhibit C and calculation schedule](https://www.sec.gov/Archives/edgar/data/1408356/000119312512416770/d229977dex1010.htm).

**Implementation implication:** each rendered draft should preserve:

- controlling agreement/amendment/waiver ID, effective date, clause and page/span;
- source financial fact, period, units, ledger/statement locator, transformation and
  adjustment evidence for every input;
- deterministic calculation steps, threshold-selection reason, headroom and output;
- preparer, reviewer, decision, timestamp and immutable revision history.

The UI should label output `DRAFT_COMPLIANT`, `DRAFT_BREACH`, or `NEEDS_REVIEW`.
It must not state that an AI has legally certified compliance; the agreement’s
authorized officer remains the signer.

## 3. Review and safe-abstention controls

Route to `NEEDS_REVIEW` if the controlling version is unresolved; a definition or
cross-reference cannot be resolved; an input/adjustment lacks evidence; periods,
currency, scope or units do not reconcile; a threshold/activation condition is
uncertain; or OCR makes a decimal, date, or inequality unclear. Do not treat missing
values as zero, and do not produce a pass until all required evidence is present.

This is consistent with real agreements’ escalation mechanisms. In one filed credit
agreement, a material pro-forma EBITDA change for an acquisition requires an audit,
third-party diligence report satisfactory to the administrative agent, **or** required
lender approval. [SEC-filed agreement amendment, Section 2.5(g)](https://www.sec.gov/Archives/edgar/data/1157408/000110465920098434/tm2029072d2_10-1.htm).
So reviewer acceptance must be a recorded decision with rationale and supporting
document—not a silent model override.

For public-company deployments, the control posture also aligns with the SEC’s
definition of internal control over financial reporting: records must accurately and
fairly reflect transactions; transactions require appropriate authorization; and
unauthorized asset use/disposition must be prevented or detected promptly. [17 C.F.R.
§ 240.13a-15](https://www.ecfr.gov/current/title-17/chapter-II/part-240/section-240.13a-15). That rule does not
itself prescribe a loan-covenant product, but it supports the design inference that
source lineage, authorized approvals, access control, and tamper-evident history are
essential safeguards. SEC rules also require principal executive and financial officers
to sign specified periodic-report certifications; this reinforces preserving a human
sign-off boundary. [SEC Rule 13a-14 final rule](https://www.sec.gov/files/rules/final/33-8124.htm).

## Demo checklist

1. Use the same financial package against two agreement rule sets whose DSCR/leverage
   definitions differ, and show different draft outcomes.
2. Display the definition chain, source facts, adjustment support, arithmetic and the
   selected threshold beside the draft certificate.
3. Demonstrate a missing add-back, unclear amendment, or low-confidence extraction
   ending in `NEEDS_REVIEW`; show an authorized reviewer’s recorded resolution and
   recalculation.
4. Keep arithmetic deterministic and allow-list the expression operations. The model
   may propose extraction/mapping, but may not silently alter rules, inputs, or verdicts.
