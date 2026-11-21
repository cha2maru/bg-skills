"""bg serve：対局を画面で見て、さわれるようにする（ゲームエンジンではない。操作は bg op と同じ記録に残る）。

GET  /            画面（ui.html）
GET  /api/def     定義の要約（エリアの木・種類・ルール・用語・進行状態・プレイヤー）
GET  /api/view?as=P&meaning=1   見え方（as 省略でキーパー）
GET  /api/log     操作の記録
POST /api/op      操作を 1 つ（JSON）。エージェントは bg op でも同じ対局を操作できる
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from .definition import table_layout
from .session import Session
from .view import view, visibility


def _area_tree(d, areas):
    out = []
    for a in areas or []:
        out.append({"id": a["id"], "name": a.get("name"), "text": d.text_of(a["id"]), "kind": a.get("kind"),
                    "pos": a.get("pos"), "owner": a.get("owner"), "ordered": bool(a.get("ordered") or any(
                        d.kinds[k].get("ordered") for k in d.kind_chain(a.get("kind")))),
                    "visibility": visibility(d, a["id"]), "shape": a.get("shape"), "hex": bool(a.get("hex")),
                    "xy": a.get("xy"), "angle": a.get("angle"), "image": d.image(a["id"]), "rect": a.get("rect"), "poly": a.get("poly"), "path": a.get("path"), "viewbox": a.get("viewbox"), "color": a.get("color"), "aspect": a.get("aspect"), "folded": bool(a.get("folded")),
                    "areas": _area_tree(d, a.get("areas"))})
    return out


def definition_summary(s: Session) -> dict:
    d = s.defn
    return {
        "game": d.data["game"], "players": d.data["players"], "seats": s.meta["seats"],
        "assets": {"credit": (d.data.get("assets") or {}).get("credit"), "images": bool(d.assets_root())},
        "areas": _area_tree(d, d.data["areas"]),
        "kinds": {k: {"base": v.get("base"), "name": v.get("name"), "text": v.get("text"), "states": d.states(k), "uses": d.uses(k),
                      "show_state": [f for kk in d.kind_chain(k) for f in d.kinds[kk].get("show_state") or []]}
                  for k, v in d.kinds.items()},
        "parts": {pid: {"kind": p.get("kind"), "attributes": p.get("attributes"), "distinct": d.distinct(pid)}
                  for pid, p in d.parts.items()},
        "rules": d.data.get("rules") or [], "terms": d.terms, "progress": d.data.get("progress") or {},
        "groups": d.data.get("groups") or {}, "links": d.data.get("links") or [],
        "table": table_layout(d), "actions": d.data.get("actions") or [], "metrics": d.data.get("metrics") or [], "flow": d.data.get("flow"),
    }


def make_handler(session_dir):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):  # 標準エラーを汚さない
            pass

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                s = Session(session_dir)
                if u.path == "/":
                    self._send(200, files("bgskills").joinpath("ui.html").read_bytes(), "text/html; charset=utf-8")
                elif u.path == "/api/def":
                    self._send(200, definition_summary(s))
                elif u.path == "/api/view":
                    self._send(200, view(s.defn, s.state(), q.get("as") or None, q.get("meaning") == "1", s.meta["seats"]))
                elif u.path.startswith("/assets/"):  # 定義の画像（assets.root の下だけ）
                    from urllib.parse import unquote
                    root = s.defn.assets_root()
                    f = (root / unquote(u.path[len("/assets/"):])).resolve() if root else None
                    if not f or not f.is_relative_to(root) or not f.is_file():
                        return self._send(404, {"error": "not found"})
                    ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml"}.get(f.suffix.lower())
                    if not ctype:
                        return self._send(404, {"error": "not found"})
                    self._send(200, f.read_bytes(), ctype)
                elif u.path == "/api/log":  # 見る立場（as）で伏せる。省けばキーパー
                    from .redact import visible_log
                    who = (parse_qs(u.query).get("as") or [None])[0] or None
                    self._send(200, visible_log(s, who))
                elif u.path == "/api/candidates":  # アクションの引数の候補と条件（SPC-052）
                    from .query import candidates
                    args = json.loads(q["args"]) if q.get("args") else None
                    from .redact import visible_candidates  # 見えていない部品は候補に出さない
                    st = s.state()
                    self._send(200, visible_candidates(s.defn, st, q["by"], candidates(s.defn, st, q["action"], q["by"], q["param"], args)))
                else:
                    self._send(404, {"error": "not found"})
            except (ValueError, KeyError) as e:  # OpError・DefinitionError・式の誤りも ValueError
                self._send(400, {"error": str(e)})

        def do_POST(self):
            path = urlparse(self.path).path
            if path not in ("/api/op", "/api/action"):
                return self._send(404, {"error": "not found"})
            try:
                op = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                s = Session(session_dir)
                if path == "/api/action":  # {"action": "draw", "by": "P1", "args": {...}}
                    s.act(op["action"], op["by"], op.get("args"))
                else:
                    s.apply(op)
                self._send(200, {"ok": True, "seq": len(s.log()), "warnings": s.last_warnings})
            except (ValueError, KeyError) as e:
                self._send(400, {"error": str(e)})

    return H


def serve(session_dir, host="127.0.0.1", port=8765):
    httpd = ThreadingHTTPServer((host, port), make_handler(session_dir))
    print(f"http://{host}:{port}/  （対局：{session_dir}。Ctrl+C で止める）", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return httpd
