"""Live validation script reproducing Section 14 manual test sequence against running web app.
"""

import json
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

def main():
    base_url = "http://127.0.0.1:5000"
    cj = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPRedirectHandler()
    )

    unique_email = f"livetester_{int(time.time())}@chronicle.local"
    print(f"[1] Signing up new test user: {unique_email}...")
    signup_data = urllib.parse.urlencode({
        "name": "Live Tester",
        "email": unique_email,
        "gender": "Other",
        "dob": "1992-02-02",
        "password": "mypassword123",
        "confirm_password": "mypassword123",
    }).encode("utf-8")
    
    req = urllib.request.Request(f"{base_url}/signup", data=signup_data, method="POST")
    res = opener.open(req)
    assert res.status == 200
    print("User registered and authenticated.")

    # STEP 1: Save program 'Even Number'
    print("\n[STEP 1] Saving program 'Even Number'...")
    even_code = "start = 1\nend = 20\nfor num in range(start, end + 1):\n    if num % 2 == 0:\n        print(num)\n"
    save_payload = json.dumps({
        "name": "Even Number",
        "source_code": even_code,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/programs/save",
        data=save_payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        res = opener.open(req)
        raw_res = res.read().decode("utf-8")
        even_data = json.loads(raw_res)
        even_id = even_data["program"]["id"]
    except urllib.error.HTTPError as e:
        print("HTTP Error Body:", e.read().decode("utf-8"))
        raise
    print(f"Created Even Number with ID={even_id}")

    # Verify Even Number workspace page
    req = urllib.request.Request(f"{base_url}/programs/{even_id}")
    even_html = opener.open(req).read().decode("utf-8")
    assert "Even Number" in even_html
    assert "range(start, end + 1)" in even_html
    print("Verified Even Number workspace view contains original code.")

    # STEP 2: Request New Program workspace via /programs (Simulating +)
    print("\n[STEP 2] Simulating '+' button (navigating to /programs)...")
    req = urllib.request.Request(f"{base_url}/programs")
    new_html = opener.open(req).read().decode("utf-8")
    assert 'value="Untitled Program"' in new_html
    assert 'value=""' in new_html
    assert "range(start, end + 1)" not in new_html
    assert "No output yet." in new_html
    print("Verified New Program workspace is completely blank, titled 'Untitled Program', with 'No output yet.'")

    # STEP 3 & 4: Enter and Save 'Odd Number'
    print("\n[STEP 3 & 4] Saving 'Odd Number' as a new program...")
    odd_code = "for num in range(1, 10):\n    if num % 2 != 0:\n        print(num)\n"
    save_payload = json.dumps({
        "name": "Odd Number",
        "source_code": odd_code,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/programs/save",
        data=save_payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    res = opener.open(req)
    raw_odd = res.read().decode("utf-8")
    odd_data = json.loads(raw_odd)
    odd_id = odd_data["program"]["id"]
    print(f"Created Odd Number with ID={odd_id}")
    assert odd_id != even_id, "Odd Number must have a distinct ID!"

    # STEP 5: Reopen 'Even Number'
    print("\n[STEP 5] Reopening 'Even Number'...")
    req = urllib.request.Request(f"{base_url}/programs/{even_id}")
    even_reopen = opener.open(req).read().decode("utf-8")
    assert "range(start, end + 1)" in even_reopen
    assert "range(1, 10)" not in even_reopen
    print("Verified 'Even Number' still contains its original code!")

    # STEP 6: Reopen 'Odd Number'
    print("\n[STEP 6] Reopening 'Odd Number'...")
    req = urllib.request.Request(f"{base_url}/programs/{odd_id}")
    odd_reopen = opener.open(req).read().decode("utf-8")
    assert "range(1, 10)" in odd_reopen
    assert "start = 1" not in odd_reopen
    print("Verified 'Odd Number' contains its new code!")

    # STEP 7: Run both programs
    print("\n[STEP 7] Running both programs...")
    req = urllib.request.Request(f"{base_url}/api/programs/{even_id}/run", data=json.dumps({}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    run_even_data = json.loads(opener.open(req).read().decode("utf-8"))
    assert run_even_data["result"]["status"] == "SUCCESS"
    assert "2\n4\n6\n8" in run_even_data["result"]["stdout"]
    print(f"Even Number run output:\n{run_even_data['result']['stdout'].strip()}")

    req = urllib.request.Request(f"{base_url}/api/programs/{odd_id}/run", data=json.dumps({}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    run_odd_data = json.loads(opener.open(req).read().decode("utf-8"))
    assert run_odd_data["result"]["status"] == "SUCCESS"
    assert "1\n3\n5\n7\n9" in run_odd_data["result"]["stdout"]
    print(f"Odd Number run output:\n{run_odd_data['result']['stdout'].strip()}")

    # STEP 8: History check
    print("\n[STEP 8] Checking Execution History...")
    req = urllib.request.Request(f"{base_url}/history")
    hist_html = opener.open(req).read().decode("utf-8")
    assert "Even Number" in hist_html
    assert "Odd Number" in hist_html
    print("History verified with both execution records.")

    print("\n=== ALL 8 VALIDATION STEPS PASSED PERFECTLY ===")

if __name__ == "__main__":
    main()
