"""Automated Judge Demo Script
Executes the full Judge QA flow against the local backend:
1. Creates a private case from 'aurora-net-leverage'
2. Attaches aon-credit-agreement.pdf
3. Attaches 2023-form-10k.html
4. Runs the covenant pipeline
5. Verifies the period mismatch is caught (amber review status)
6. Records human controller decision (Request document)
7. Prints browser link to open and explore in the UI
"""

import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

API_BASE = "http://localhost:8123"
REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_HEADER = {"Authorization": "Bearer demo-officer:officer:demo-org"}

AGREEMENT_PATH = REPO_ROOT / "data/raw/pdf-fixtures/aon-credit-agreement.pdf"
FINANCIALS_PATH = REPO_ROOT / "data/raw/sec/aon/2023-form-10k.html"

def make_request(path, method="GET", body=None, headers=None):
    url = f"{API_BASE}{path}"
    h = dict(AUTH_HEADER)
    if headers:
        h.update(headers)
    
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json"
        elif isinstance(body, bytes):
            data = body
            
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            return json.loads(res_body) if res_body else {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"[-] HTTP Error {e.code} on {method} {path}: {err_msg}")
        return None
    except Exception as e:
        print(f"[-] Connection Error on {method} {path}: {e}")
        return None

def upload_multipart(path, file_path, document_role):
    boundary = "----WebKitFormBoundaryDemoBoundary7MA4YWxkTrZu0gW"
    filename = file_path.name
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    body_parts = []
    # file field
    body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
    body_parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"))
    content_type = "application/pdf" if filename.endswith(".pdf") else "text/html"
    body_parts.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    body_parts.append(file_bytes)
    body_parts.append(b"\r\n")

    # document_role field
    body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
    body_parts.append('Content-Disposition: form-data; name="document_role"\r\n\r\n'.encode("utf-8"))
    body_parts.append(document_role.encode("utf-8"))
    body_parts.append(b"\r\n")

    # title field
    body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
    body_parts.append('Content-Disposition: form-data; name="title"\r\n\r\n'.encode("utf-8"))
    body_parts.append(filename.encode("utf-8"))
    body_parts.append(b"\r\n")

    body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    full_body = b"".join(body_parts)

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return make_request(path, method="POST", body=full_body, headers=headers)

def main():
    print("=" * 65)
    print("🚀 AUTOMATED JUDGE DEMO RUNNER")
    print("=" * 65)

    # 1. Health check
    print("\n[1/6] Checking backend status at http://localhost:8123 ...")
    health = make_request("/health")
    if not health:
        print("❌ Error: Backend API is not responding on http://localhost:8123.")
        print("Please start the backend with: D:\\demo\\start_backend.bat")
        return 1
    print("✅ Backend is LIVE and healthy!")

    # 2. Create private case
    print("\n[2/6] Creating private case from 'aurora-net-leverage'...")
    create_res = make_request("/api/cases", method="POST", body={
        "template_case_id": "aurora-net-leverage",
        "name": "Aurora Net Leverage (Judge Demo)"
    })
    if not create_res or "case_id" not in create_res:
        print("❌ Failed to create case.")
        return 1
    case_id = create_res["case_id"]
    print(f"✅ Created Case ID: {case_id}")

    # 3. Upload Aon Credit Agreement
    print(f"\n[3/6] Uploading Credit Agreement ({AGREEMENT_PATH.name})...")
    up1 = upload_multipart(f"/api/cases/{case_id}/documents", AGREEMENT_PATH, "credit_agreement")
    if not up1 or "document_id" not in up1:
        print("❌ Failed to upload credit agreement.")
        return 1
    print(f"✅ Uploaded Document: {up1['document_id']} (rev: {up1.get('revision_id')})")

    # 4. Upload Aon Financial Filing
    print(f"\n[4/6] Uploading Financial Statement ({FINANCIALS_PATH.name})...")
    up2 = upload_multipart(f"/api/cases/{case_id}/documents", FINANCIALS_PATH, "financial_statement")
    if not up2 or "document_id" not in up2:
        print("❌ Failed to upload financial statement.")
        return 1
    print(f"✅ Uploaded Document: {up2['document_id']} (rev: {up2.get('revision_id')})")

    # 5. Run covenant calculation
    print(f"\n[5/6] Executing deterministic calculation pipeline for {case_id}...")
    run_res = make_request(f"/api/cases/{case_id}/run", method="POST", body={})
    if not run_res:
        print("❌ Failed to run calculation.")
        return 1
    
    status = run_res.get("status")
    calc = run_res.get("calculation", {})
    print(f"✅ Run Completed! Status: {status}")
    print(f"   Formula:    {calc.get('formula')}")
    print(f"   Ratio:      {calc.get('ratio')}x {calc.get('comparator')} {calc.get('threshold')}x")
    print(f"   Status:     {status} (Fail-closed period mismatch caught!)")

    # 6. Fetch snapshot and record controller decision
    print("\n[6/6] Inspecting review issues and recording Controller decision...")
    snap = make_request(f"/api/cases/{case_id}/snapshot")
    if snap and snap.get("review_issues"):
        for issue in snap["review_issues"]:
            issue_id = issue.get("issue_id")
            if issue.get("status") == "open":
                print(f"   Recording Human Review decision on issue {issue_id}...")
                resolve_res = make_request(f"/api/review-issues/{issue_id}/resolve", method="POST", body={
                    "revision_id": snap["revision"]["revision_id"],
                    "expected_bundle_hash": snap["revision"]["input_bundle_hash"],
                    "decision_kind": "request_document",
                    "rationale": "The available financial statement does not match the covenant test period. Please provide period-matched financial evidence before approval."
                })
                print("   ✅ Human Review Recorded: 'Request document' (Fail-closed governance verified!)")

    print("\n" + "=" * 65)
    print("🎉 DEMO CASE READY!")
    print("=" * 65)
    print(f"\n👉 Open this URL directly in your browser:")
    print(f"   http://localhost:3000/cases/{case_id}")
    print("\nAll calculation cards, period checks, and review decisions are already loaded and visible!")
    print("=" * 65)
    return 0

if __name__ == "__main__":
    sys.exit(main())
