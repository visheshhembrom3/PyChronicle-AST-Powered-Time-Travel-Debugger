"""Integration tests for PyChronicle Web Server REST API and static asset endpoints."""

import json
from pathlib import Path
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from pychronicle.web.server import PyChronicleServer


def test_web_server_rest_api_lifecycle():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "web_test.db"
        server = PyChronicleServer(host="127.0.0.1", port=18080, db_path=db_path)
        actual_port = server.start()
        base_url = f"http://127.0.0.1:{actual_port}"

        try:
            # 1. Test Health
            req = urllib.request.urlopen(f"{base_url}/api/health")
            assert req.status == 200
            data = json.loads(req.read().decode("utf-8"))
            assert data["status"] == "ok"
            assert data["app"] == "PyChronicle"

            # 2. Test Static Files (index.html, style.css, app.js)
            for path in ["/", "/style.css", "/app.js"]:
                res = urllib.request.urlopen(f"{base_url}{path}")
                assert res.status == 200
                assert len(res.read()) > 0

            # 3. Test List Programs (Default seeded program)
            res = urllib.request.urlopen(f"{base_url}/api/programs")
            assert res.status == 200
            progs = json.loads(res.read().decode("utf-8"))["programs"]
            assert len(progs) >= 1
            first_prog_id = progs[0]["id"]

            # 4. Create New Program via POST /api/programs
            new_prog_payload = json.dumps({
                "name": "Web API Test Program",
                "description": "Created via REST API test",
                "source_code": "a = 100\nb = 200\nc = a + b\nprint('Sum:', c)\n",
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url}/api/programs",
                data=new_prog_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            res = urllib.request.urlopen(req)
            assert res.status == 201
            created = json.loads(res.read().decode("utf-8"))["program"]
            created_id = created["id"]
            assert created["name"] == "Web API Test Program"

            # 5. Run Program via POST /api/programs/<id>/run
            run_payload = json.dumps({
                "source_code": "a = 100\nb = 200\nc = a + b\nprint('Sum:', c)\n",
                "watch_vars": ["a", "b", "c"],
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url}/api/programs/{created_id}/run",
                data=run_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            res = urllib.request.urlopen(req)
            assert res.status == 200
            exec_res = json.loads(res.read().decode("utf-8"))
            assert exec_res["status"] == "SUCCESS"
            assert "Sum: 300" in exec_res["stdout"]
            assert exec_res["total_steps"] > 0
            exec_id = exec_res["execution_id"]

            # 6. Replay Step via GET /api/executions/<id>/replay/<step>?watch=a,b,c
            res = urllib.request.urlopen(f"{base_url}/api/executions/{exec_id}/replay/{exec_res['total_steps']}?watch=a,b,c")
            assert res.status == 200
            replay_data = json.loads(res.read().decode("utf-8"))
            assert replay_data["step"] == exec_res["total_steps"]
            assert replay_data["scopes"]["<module>"]["c"] == "300"
            assert replay_data["watch_values"]["c"] == "300"

            # 7. Get Executions list for program
            res = urllib.request.urlopen(f"{base_url}/api/programs/{created_id}/executions")
            assert res.status == 200
            exec_list = json.loads(res.read().decode("utf-8"))["executions"]
            assert len(exec_list) == 1
            assert exec_list[0]["id"] == exec_id

            # 8. Duplicate Program via POST /api/programs/<id>/duplicate
            dup_payload = json.dumps({}).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url}/api/programs/{created_id}/duplicate",
                data=dup_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            res = urllib.request.urlopen(req)
            assert res.status == 201
            dup_prog = json.loads(res.read().decode("utf-8"))["program"]
            assert dup_prog["name"] == "Web API Test Program Copy"

            # 9. Delete Program via DELETE /api/programs/<id>
            req = urllib.request.Request(
                f"{base_url}/api/programs/{created_id}",
                method="DELETE",
            )
            res = urllib.request.urlopen(req)
            assert res.status == 200
            del_res = json.loads(res.read().decode("utf-8"))
            assert del_res["success"] is True

        finally:
            server.stop()
