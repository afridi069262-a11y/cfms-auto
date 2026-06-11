"""
CMS Auto — Web Interface for fast_runner.py
Flask backend: handles session login, prosecutor list, input data, and script execution.
"""

import os, json, threading, time, queue, tempfile, traceback, re
from flask import Flask, request, jsonify, render_template, Response
from fast_runner import (
    ApiSession, parse_case, process_case, DECISION_MAPPING, BASE_URL
)
import requests, urllib.parse

app = Flask(__name__)

# ── In-memory state ────────────────────────────────────────
_state = {
    "session": None,
    "log_queue": queue.Queue(),
    "running": False,
    "stats": {"total": 0, "success": 0, "skip": 0, "invalid": 0},
    "prosecutors": [],
}

# ── Logging bridge ─────────────────────────────────────────
import logging

class QueueHandler(logging.Handler):
    def emit(self, record):
        _state["log_queue"].put(self.format(record))

_queue_handler = QueueHandler()
_queue_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(_queue_handler)


# ── Routes ─────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"ok": False, "msg": "Username aur password dono chahiye"})

    try:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/143 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": BASE_URL,
            "Referer": BASE_URL + "/",
            "X-Requested-With": "XMLHttpRequest",
        })
        r0 = s.get(BASE_URL + "/", timeout=15)
        xsrf_raw = ""
        for c in s.cookies:
            if c.name == "XSRF-TOKEN":
                xsrf_raw = urllib.parse.unquote(c.value)
                break
        s.headers["X-XSRF-TOKEN"] = xsrf_raw

        r = s.post(BASE_URL + "/login", json={
            "email": username,
            "password": password,
        }, timeout=15, allow_redirects=True)

        if r.status_code not in [200, 201]:
            return jsonify({"ok": False, "msg": f"Login fail — HTTP {r.status_code}"})

        resp_data = {}
        try:
            resp_data = r.json()
        except Exception:
            pass

        if isinstance(resp_data, dict) and resp_data.get("message", "").lower() in ["unauthenticated.", "invalid credentials"]:
            return jsonify({"ok": False, "msg": "Invalid credentials"})

        for c in s.cookies:
            if c.name == "XSRF-TOKEN":
                xsrf_raw = urllib.parse.unquote(c.value)
                break
        s.headers["X-XSRF-TOKEN"] = xsrf_raw

        rv = s.get(BASE_URL + "/get-dashboard-stats", timeout=15)
        if rv.status_code != 200:
            return jsonify({"ok": False, "msg": f"Session verify nahi hua (HTTP {rv.status_code})"})

        api = ApiSession()
        api.session = s
        api.load_master_data()
        _state["session"] = api

        return jsonify({"ok": True, "msg": "✅ Login successful! Session active hai."})

    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error: {str(e)}"})


@app.route("/api/session-manual", methods=["POST"])
def api_session_manual():
    data = request.json or {}
    xsrf = data.get("xsrf", "").strip()
    # Parse full cURL if sent
    curl_text = data.get("curl_text","")
    if curl_text:
        bm = re.search(r"-b '([^']+)'", curl_text)
        if bm:
            cs = bm.group(1)
            xm = re.search(r'XSRF-TOKEN=([^;]+)', cs)
            sm = re.search(r'prosecution_department_of_punjab_session=([^;]+)', cs)
            if xm: data["xsrf_raw"] = xm.group(1).strip()
            if sm: data["session_raw"] = sm.group(1).strip()
    session_cookie = data.get("session_cookie", "").strip()
    if not xsrf or not session_cookie:
        return jsonify({"ok": False, "msg": "XSRF-TOKEN aur session cookie dono chahiye"})
    try:
        import urllib.parse as _up
        session_data = {
            "cookies": {
                "XSRF-TOKEN": xsrf,
                "prosecution_department_of_punjab_session": session_cookie,
            },
            "xsrf_token": xsrf,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
        json.dump(session_data, tmp)
        tmp.close()
        api = ApiSession()
        import fast_runner as fr
        orig = fr.SESSION_FILE
        fr.SESSION_FILE = tmp.name
        ok = api.load_session()
        fr.SESSION_FILE = orig
        os.unlink(tmp.name)
        if not ok:
            return jsonify({"ok": False, "msg": "Session load nahi hua"})
        api.refresh_xsrf()
        import requests as _req
        _xr = data.get("xsrf_raw") or xsrf
        _sr = data.get("session_raw") or session_cookie
        print("DEBUG xr_len:", len(_xr), "sr_len:", len(_sr))
        _pr = _req.get(
            BASE_URL + "/get-prosecutors-select2",
            headers={
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
                "X-XSRF-TOKEN": _xr,
                "Referer": BASE_URL + "/",
                "Cookie": "XSRF-TOKEN=" + _xr + "; prosecution_department_of_punjab_session=" + _sr,
            },
            timeout=15
        )
        print("DEBUG PROS_STATUS:", _pr.status_code)
        prosecutors = []
        if _pr.status_code == 200:
            try:
                for x in _pr.json():
                    name_raw = x.get("text", "")
                    name = name_raw.split("\r\n")[0].strip() if "\r\n" in name_raw else name_raw.strip()
                    prosecutors.append({"id": x.get("id"), "name": name})
            except Exception:
                pass
        api.load_master_data()
        _state["session"] = api
        _state["prosecutors"] = prosecutors
        return jsonify({"ok": True, "msg": "✅ Session active hai!", "prosecutors": prosecutors})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error: {str(e)}"})



@app.route("/api/get-prosecutors", methods=["GET"])
def api_get_prosecutors():
    if not _state.get("session"):
        return jsonify({"ok": False, "msg": "Pehle login karo"})
    cached = _state.get("prosecutors", [])
    if cached:
        return jsonify({"ok": True, "prosecutors": cached})
    # fallback: fresh fetch
    try:
        api = _state["session"]
        api.refresh_xsrf()
        r = api.session.get(BASE_URL + "/get-prosecutors-select2", timeout=15)
        if r.status_code != 200:
            return jsonify({"ok": False, "msg": f"HTTP {r.status_code}"})
        items = r.json()
        result = []
        if isinstance(items, list):
            for x in items:
                name_raw = x.get("text", "")
                name = name_raw.split("\r\n")[0].strip() if "\r\n" in name_raw else name_raw.strip()
                result.append({"id": x.get("id"), "name": name})
        _state["prosecutors"] = result
        return jsonify({"ok": True, "prosecutors": result})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})


@app.route("/api/set-prosecutor", methods=["POST"])
def api_set_prosecutor():
    data = request.json or {}
    pid = data.get("prosecutor_id")
    api = _state.get("session")
    if not api:
        return jsonify({"ok": False, "msg": "Pehle login karo"})
    try:
        api.prosecutor_id = int(pid)
        return jsonify({"ok": True, "msg": f"Prosecutor ID set: {pid}"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})


@app.route("/api/run", methods=["POST"])
def api_run():
    if _state["running"]:
        return jsonify({"ok": False, "msg": "Script abhi bhi chal rahi hai. Ruko."})

    api = _state.get("session")
    if not api:
        return jsonify({"ok": False, "msg": "Pehle login karo"})

    data = request.json or {}
    input_text = data.get("input_text", "").strip()
    if not input_text:
        return jsonify({"ok": False, "msg": "Input data empty hai"})

    lines = [l for l in input_text.splitlines() if l.strip()]
    if not lines:
        return jsonify({"ok": False, "msg": "Koi valid line nahi mili"})

    _state["stats"] = {"total": 0, "success": 0, "skip": 0, "invalid": 0}
    _state["running"] = True

    def runner():
        try:
            api.refresh_xsrf()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                _state["stats"]["total"] += 1
                status = process_case(api, line)
                if status == "COMPLETE":
                    _state["stats"]["success"] += 1
                elif status == "SKIP":
                    _state["stats"]["skip"] += 1
                elif status == "INVALID":
                    _state["stats"]["invalid"] += 1
                time.sleep(0.5)
            _state["log_queue"].put("__DONE__")
        except Exception as e:
            _state["log_queue"].put(f"ERROR: {traceback.format_exc()}")
            _state["log_queue"].put("__DONE__")
        finally:
            _state["running"] = False

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return jsonify({"ok": True, "msg": "Script shuru ho gayi!"})


@app.route("/api/stream-logs")
def stream_logs():
    def generate():
        yield "data: {\"type\":\"connected\"}\n\n"
        while True:
            try:
                msg = _state["log_queue"].get(timeout=30)
                if msg == "__DONE__":
                    stats = _state["stats"]
                    yield f"data: {{\"type\":\"done\", \"stats\": {json.dumps(stats)}}}\n\n"
                    break
                yield f"data: {json.dumps({'type':'log','msg': msg})}\n\n"
                if "CASE_INVALID:" in msg:
                    try:
                        import json as _j
                        payload = msg.split("CASE_INVALID:",1)[1].strip()
                        cdata = _j.loads(payload)
                        yield f"data: {json.dumps({'type':'case_invalid','case':cdata})}\n\n"
                    except Exception:
                        pass
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/status")
def api_status():
    return jsonify({
        "logged_in": _state["session"] is not None,
        "running": _state["running"],
        "stats": _state["stats"],
        "prosecutor_id": _state["session"].prosecutor_id if _state["session"] else None,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
