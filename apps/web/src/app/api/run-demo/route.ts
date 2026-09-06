import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";

const API_BASE = process.env.AGENT_URL || "http://localhost:8123";
const AUTH_HEADER = "Bearer demo-officer:officer:demo-org";

export async function GET() {
  try {
    const rootDir = path.resolve(process.cwd(), "..", "..");
    const agreementPath = path.join(rootDir, "data", "raw", "pdf-fixtures", "aon-credit-agreement.pdf");
    const financialsPath = path.join(rootDir, "data", "raw", "sec", "aon", "2023-form-10k.html");

    if (!fs.existsSync(agreementPath) || !fs.existsSync(financialsPath)) {
      return NextResponse.json({
        error: "Fixture files not found",
        agreementPath,
        financialsPath,
      }, { status: 404 });
    }

    // 1. Create private case
    const createRes = await fetch(`${API_BASE}/api/cases`, {
      method: "POST",
      headers: {
        "Authorization": AUTH_HEADER,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        template_case_id: "aurora-net-leverage",
        name: "Aurora Net Leverage (Judge Demo)",
      }),
    });

    if (!createRes.ok) {
      const err = await createRes.text();
      return NextResponse.json({ step: "create_case", error: err }, { status: createRes.status });
    }
    const { case_id } = await createRes.json();

    // 2. Upload Credit Agreement
    const agreementBytes = fs.readFileSync(agreementPath);
    const agreementBlob = new Blob([agreementBytes], { type: "application/pdf" });
    const form1 = new FormData();
    form1.append("file", agreementBlob, "aon-credit-agreement.pdf");
    form1.append("document_role", "credit_agreement");
    form1.append("title", "aon-credit-agreement.pdf");

    const upRes1 = await fetch(`${API_BASE}/api/cases/${case_id}/documents`, {
      method: "POST",
      headers: { "Authorization": AUTH_HEADER },
      body: form1,
    });
    if (!upRes1.ok) {
      const err = await upRes1.text();
      return NextResponse.json({ step: "upload_agreement", error: err }, { status: upRes1.status });
    }

    // 3. Upload Financial Statement
    const financialsBytes = fs.readFileSync(financialsPath);
    const financialsBlob = new Blob([financialsBytes], { type: "text/html" });
    const form2 = new FormData();
    form2.append("file", financialsBlob, "2023-form-10k.html");
    form2.append("document_role", "financial_statement");
    form2.append("title", "2023-form-10k.html");

    const upRes2 = await fetch(`${API_BASE}/api/cases/${case_id}/documents`, {
      method: "POST",
      headers: { "Authorization": AUTH_HEADER },
      body: form2,
    });
    if (!upRes2.ok) {
      const err = await upRes2.text();
      return NextResponse.json({ step: "upload_financials", error: err }, { status: upRes2.status });
    }

    // 4. Run calculation pipeline
    const runRes = await fetch(`${API_BASE}/api/cases/${case_id}/run`, {
      method: "POST",
      headers: {
        "Authorization": AUTH_HEADER,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });
    const runData = runRes.ok ? await runRes.json() : null;

    // 5. Inspect snapshot and record human review decision
    const snapRes = await fetch(`${API_BASE}/api/cases/${case_id}/snapshot`, {
      headers: { "Authorization": AUTH_HEADER },
    });
    const snapData = snapRes.ok ? await snapRes.json() : null;

    let reviewRecorded = false;
    if (snapData && snapData.review_issues) {
      for (const issue of snapData.review_issues) {
        if (issue.status === "open") {
          await fetch(`${API_BASE}/api/review-issues/${issue.issue_id}/resolve`, {
            method: "POST",
            headers: {
              "Authorization": AUTH_HEADER,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              revision_id: snapData.revision.revision_id,
              expected_bundle_hash: snapData.revision.input_bundle_hash,
              decision_kind: "request_document",
              rationale: "The available financial statement does not match the covenant test period. Please provide period-matched financial evidence before approval.",
            }),
          });
          reviewRecorded = true;
        }
      }
    }

    return NextResponse.json({
      success: true,
      case_id,
      url: `http://localhost:3000/cases/${case_id}`,
      calculation: runData?.calculation,
      status: runData?.status,
      reviewRecorded,
    });
  } catch (error) {
    return NextResponse.json({
      error: error instanceof Error ? error.message : String(error),
    }, { status: 500 });
  }
}
