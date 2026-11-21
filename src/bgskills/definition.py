"""ゲーム定義：YAML を読み、略記を展開し、要素を ID で引けるようにする（SPC-001・004・005）。"""
from __future__ import annotations

import copy
import itertools
import re
from pathlib import Path

import yaml


class DefinitionError(ValueError):
    pass


_VAR = re.compile(r"\{(\w+)\}")
BOX = "box"


def fill(value, env):
    """文字列の中の {var} を env の値で置き換える。文字列全体が {var} なら値の型を保つ。"""
    if isinstance(value, str):
        m = _VAR.fullmatch(value)
        if m and m.group(1) in env:
            return env[m.group(1)]
        return _VAR.sub(lambda m: str(env[m.group(1)]) if m.group(1) in env else m.group(0), value)
    if isinstance(value, list):
        return [fill(v, env) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, env) for k, v in value.items()}
    return value


def _envs(item, players):
    """for_each（と copies）の組み合わせごとの変数の束を返す。"""
    loops = dict(item.get("for_each") or {})
    for k, v in loops.items():
        if v == "players":
            loops[k] = players
    if "copies" in item:
        loops["copy"] = list(range(1, item["copies"] + 1))
    keys = list(loops)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(loops[k] for k in keys))]


def _expand_list(items, players):
    out = []
    for item in items or []:
        bare = {k: v for k, v in item.items() if k not in ("for_each", "copies")}
        for env in _envs(item, players):
            out.append(fill(copy.deepcopy(bare), env))
    return out


def _expand_areas(areas, players):
    out = []
    for a in _expand_list(areas, players):
        layout = a.pop("layout", None)
        children = _expand_areas(a.get("areas"), players)
        if layout and "hex" in layout:  # 六角の盤（半径 R）。位置はアキシャル座標 [q, r]
            R = layout["hex"]["radius"]
            for q in range(-R, R + 1):
                for r in range(max(-R, -q - R), min(R, -q + R) + 1):
                    children.append({"id": fill(layout["child_id"], {"q": q, "r": r}),
                                     "kind": layout.get("child_kind"), "pos": [q, r]})
            a["hex"] = {"radius": R, "links": layout["hex"].get("links", True)}
            if layout["hex"].get("vertices") or layout["hex"].get("edges"):
                children += _hex_corners(children, layout, a["hex"])
        if layout and "grid" in layout:
            rows, cols = layout["grid"]
            for r in range(1, rows + 1):
                for c in range(1, cols + 1):
                    children.append({"id": fill(layout["child_id"], {"row": r, "col": c}),
                                     "kind": layout.get("child_kind"), "pos": [c - 1, r - 1]})
        if children:
            a["areas"] = children
        out.append(a)
    return out


def _hex_corners(cells, layout, hexinfo):
    """マスの頂点と辺の置き場（隣のマスと共有するものは 1 つ）と、そのつながり（SPC-046）。"""
    import math
    h = layout["hex"]
    vkey, ekey, corner_of, side_of = {}, {}, {}, {}
    for c in cells:
        q, r = c["pos"]
        cx, cy = math.sqrt(3) * (q + r / 2), 1.5 * r
        pts = [(round(cx + math.cos(math.radians(60 * k - 30)), 4), round(cy + math.sin(math.radians(60 * k - 30)), 4)) for k in range(6)]
        corner_of[c["id"]] = pts
        side_of[c["id"]] = [tuple(sorted((pts[k], pts[(k + 1) % 6]))) for k in range(6)]
        for p in pts:
            vkey.setdefault(p, None)
        for e in side_of[c["id"]]:
            ekey.setdefault(e, None)
    vid = {p: fill(h.get("vertex_id", "v{n}"), {"n": i}) for i, p in enumerate(sorted(vkey, key=lambda p: (p[1], p[0])))}
    eid = {e: fill(h.get("edge_id", "e{n}"), {"n": i}) for i, e in enumerate(sorted(ekey, key=lambda e: ((e[0][1] + e[1][1]) / 2, (e[0][0] + e[1][0]) / 2)))}
    out, links = [], []
    if h.get("vertices"):
        out += [{"id": vid[p], "kind": h.get("vertex_kind"), "xy": list(p)} for p in vid]
        for c, pts in corner_of.items():
            links += [{"between": [c, vid[p]], "type": "corner"} for p in pts]
    if h.get("edges"):
        for e, i in eid.items():
            (x1, y1), (x2, y2) = e
            out.append({"id": i, "kind": h.get("edge_kind"), "xy": [round((x1 + x2) / 2, 4), round((y1 + y2) / 2, 4)],
                        "angle": round(math.degrees(math.atan2(y2 - y1, x2 - x1)), 1)})
        for c, sides in side_of.items():
            links += [{"between": [c, eid[e]], "type": "side"} for e in sides]
        if h.get("vertices"):
            for e, i in eid.items():
                links += [{"between": [vid[e[0]], i], "type": "end"}, {"between": [vid[e[0]], vid[e[1]]], "type": "adjacent"}]
                links.append({"between": [vid[e[1]], i], "type": "end"})
    hexinfo["extra_links"] = links
    return out


_HEX_DIRS = [((1, 0), "e-w"), ((1, -1), "ne-sw"), ((0, 1), "nw-se")]  # 6 方向を、2 マスの間に 1 本ずつで表す


def _hex_links(areas):
    out = []
    for a in areas or []:
        if a.get("hex") and a["hex"].get("links"):
            at = {tuple(c["pos"]): c["id"] for c in a.get("areas") or [] if "pos" in c}
            for (q, r), cid in at.items():
                for (dq, dr), typ in _HEX_DIRS:
                    other = at.get((q + dq, r + dr))
                    if other:
                        out.append({"between": [cid, other], "type": typ})
            out += a["hex"].get("extra_links") or []
        out += _hex_links(a.get("areas"))
    return out


def expand(raw: dict, players: int | None = None) -> dict:
    """略記（for_each・copies・layout）を展開した定義を返す。players は対局の人数（省略時は最大）。"""
    d = copy.deepcopy(raw)
    game = d.get("game", {})
    lo, hi = (game.get("players") or {}).get("min"), (game.get("players") or {}).get("max")
    plist = _expand_list(d.get("players"), [])
    n = players if players is not None else (hi or len(plist))
    if (lo and n < lo) or (hi and n > hi) or n > len(plist):
        raise DefinitionError(f"人数 {n} は範囲外（{lo}〜{hi}）")
    d["players"] = plist[:n]
    pids = [p["id"] for p in d["players"]]
    d["areas"] = _expand_areas(d.get("areas"), pids)
    if not any(a["id"] == BOX for a in d["areas"]):  # どの定義にも卓の外の「箱」を用意する（SPC-043）
        d["areas"].append({"id": BOX, "name": "箱", "text": "使っていない部品を入れておく箱。卓の外。",
                           "visibility": {"face": "all"}})
    d["links"] = list(d.get("links") or []) + _hex_links(d["areas"])
    d["objects"] = _expand_list(d.get("objects"), pids)
    return d


class Definition:
    """展開済みの定義と、ID からの索引。"""

    def __init__(self, raw: dict, players: int | None = None, path: str | None = None):
        self.raw = raw
        self.path = path
        self.data = expand(raw, players)
        self.areas, self.parent, self._dup = {}, {}, []
        self._walk_areas(self.data["areas"], None)
        self.parts = {o["id"]: o for o in self.data["objects"]}
        self.rules = {r["id"]: r for r in self.data.get("rules") or []}
        self.kinds = self.data.get("kinds") or {}
        self.terms = self.data.get("terms") or {}
        self.players = [p["id"] for p in self.data["players"]]
        self.index = self._build_index()

    def _walk_areas(self, areas, parent):
        for a in areas or []:
            if a["id"] in self.areas:
                self._dup.append(a["id"])
            if not a.get("owner") and parent and self.areas[parent].get("owner"):  # 持ち主は親のエリアから引き継ぐ（席の中の手札など）
                a = {**a, "owner": self.areas[parent]["owner"]}
            self.areas[a["id"]] = a
            self.parent[a["id"]] = parent
            self._walk_areas(a.get("areas"), a["id"])

    def _build_index(self):
        d = self.data
        groups = [
            ("team", (d.get("teams") or {}).items()),
            ("player", ((p["id"], p) for p in d["players"])),
            ("kind", self.kinds.items()),
            ("area", self.areas.items()),
            ("object", self.parts.items()),
            ("group", (d.get("groups") or {}).items()),
            ("term", self.terms.items()),
            ("rule", ((r["id"], r) for r in d.get("rules") or [])),
            ("ruling", ((r["id"], r) for r in d.get("rulings") or [])),
            ("progress", (d.get("progress") or {}).items()),
        ]
        index, seen = {}, {}
        dups = [(i, "area", "area") for i in self._dup]
        for kind, items in groups:
            for i, el in items:
                if i in index:
                    dups.append((i, seen[i], kind))
                index[i], seen[i] = (kind, el), kind
        if dups:
            raise DefinitionError("ID の重複: " + "、".join(f"{i}（{a} と {b}）" for i, a, b in dups))
        return index

    # --- 引く ---
    def get(self, id_):
        return self.index[id_][1]

    def kind_of(self, id_):
        """部品・エリアの種類の ID。"""
        el = self.parts.get(id_) or self.areas.get(id_) or {}
        return el.get("kind")

    def kind_chain(self, kind_id):
        chain = []
        while kind_id and kind_id in self.kinds and kind_id not in chain:
            chain.append(kind_id)
            kind_id = self.kinds[kind_id].get("base")
        return chain

    def states(self, kind_id) -> dict:
        """種類（元の種類を含む）の状態の定義：{項目: {値: 意味}}。"""
        out = {}
        for k in reversed(self.kind_chain(kind_id)):
            out.update(self.kinds[k].get("states") or {})
        return out

    def state_type(self, kind_id, field):
        """書き込む状態の型（text・player・area・number）。値を並べた状態なら None。
        例：命令書の text、投票用紙の target: player（RUL-009。紙に書くことの原型）。"""
        v = self.states(kind_id).get(field)
        return v if isinstance(v, str) else None

    def assets_root(self):
        """画像の置き場（assets.root。定義のファイルからの相対パス）。なければ None。"""
        root = (self.data.get("assets") or {}).get("root")
        if not root:
            return None
        return (Path(self.path).parent / root).resolve() if self.path else Path(root).resolve()

    def image(self, element_id, st: dict | None = None, key: str = "image"):
        """表示の画像（原型の表示方法の 1 つ）。部品かエリア → その種類の順に探す。
        値は文字列か、{"default": …, "<状態>=<値>": …}（状態で替わる絵。例：死体）。"""
        el = self.parts.get(element_id) or self.areas.get(element_id) or {}
        for src in [el] + [self.kinds[k] for k in self.kind_chain(el.get("kind"))]:
            v = src.get(key)
            if isinstance(v, dict):
                return next((p for c, p in v.items() if "=" in c and (st or {}).get(c.split("=", 1)[0]) == c.split("=", 1)[1]),
                            v.get("default"))
            if v:
                return v
        return None

    def display(self, kind_id, st: dict) -> dict:
        """部品の表示方法：状態の値の show（rotate・face）を重ねる。回転は足し合わせ、表裏は後の値が勝つ（SPC-038）。"""
        defs, rot, face, declared = self.states(kind_id), 0, "up", False
        for f, v in st.items():
            vals = defs.get(f)
            m = vals.get(v) if isinstance(vals, dict) else None
            show = m.get("show") if isinstance(m, dict) else None
            if show:
                declared = True
                rot += show.get("rotate", 0)
                face = show.get("face", face)
        if not declared:  # shortcut: show のない定義は従来の決め打ち（facing=down は裏、sideways・tapped は 90 度）
            face = "down" if st.get("facing") == "down" else "up"
            rot = 90 if any(v in ("sideways", "tapped") for v in st.values()) else 0
        return {"rotate": rot % 360, "face": face}

    def face_fields(self, kind_id) -> set:
        """表裏を決める状態の項目（値の show に face を持つ。show がなければ facing）。"""
        defs = self.states(kind_id)
        fs = {f for f, vals in defs.items() if isinstance(vals, dict)
              and any(isinstance(m, dict) and "face" in (m.get("show") or {}) for m in vals.values())}
        return fs or ({"facing"} & set(defs))

    def uses(self, kind_id) -> list:
        return [u for k in self.kind_chain(kind_id) for u in self.kinds[k].get("uses") or []]

    def text_of(self, id_):
        el = self.index.get(id_, (None, {}))[1]
        if isinstance(el, dict) and el.get("text"):
            return el["text"]
        k = self.kind_of(id_)
        for kk in self.kind_chain(k):
            if self.kinds[kk].get("text"):
                return self.kinds[kk]["text"]
        return None

    def capacity(self, area_id):
        """エリアに置ける上限（エリアか種類の capacity）。なければ None。"""
        a = self.areas.get(area_id) or {}
        if "capacity" in a:
            return a["capacity"]
        return next((self.kinds[k]["capacity"] for k in self.kind_chain(a.get("kind")) if "capacity" in self.kinds[k]), None)

    def distinct(self, part_id):
        """1 個ずつ区別する部品か（count を持つ部品・distinct: false の種類は区別しない）。"""
        p = self.parts[part_id]
        if "count" in p:
            return False
        return all(self.kinds[k].get("distinct", True) for k in self.kind_chain(p.get("kind")))


# 席の既定：人数ごとに、P1 から順に手前・…（2 人なら対面）
DEFAULT_SEATS = {1: ["bottom"], 2: ["bottom", "top"], 3: ["bottom", "left", "right"], 4: ["bottom", "left", "top", "right"],
                 # 5 人以上：時計回りに、左・上・右の辺に複数の席を並べる（手前は見る立場の 1 人）
                 5: ["bottom", "left", "top", "top", "right"], 6: ["bottom", "left", "left", "top", "right", "right"],
                 7: ["bottom", "left", "left", "top", "top", "right", "right"],
                 8: ["bottom", "left", "left", "top", "top", "top", "right", "right"]}


def table_layout(d: Definition) -> dict | None:
    """定義の table（卓の配置）を人数に合わせて解く。中央に置くエリア、席の位置、席ごとのエリア（中央に近い順）。"""
    t = d.data.get("table")
    if not t:
        return None
    n = len(d.players)
    seats = t.get("seats")
    if isinstance(seats, dict):
        seats = seats.get(n) or seats.get(str(n))
    seats = seats or DEFAULT_SEATS.get(n) or ["bottom", "left", "top", "right"] * 2
    per = {p: [fill(x, {"player": p}) for x in t.get("per_player") or []] for p in d.players}
    return {"center": list(t.get("center") or []), "seats": dict(zip(d.players, seats)), "per_player": per,
            "place": dict(t.get("place") or {})}


def merge(raw: dict, scenario: dict) -> dict:
    """シナリオ（対局ごとの非公開の設定。例：惨劇RoopeR の脚本）を定義に重ねる。並びは足し、辞書は上書きする。"""
    out = copy.deepcopy(raw)
    for k, v in (scenario or {}).items():
        if isinstance(v, list):
            out[k] = list(out.get(k) or []) + v
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def overlay(raw: dict, frag: dict) -> dict:
    """案（定義と同じ形式の断片）を重ねる（CTR-F-007・RUL-028）。辞書は中まで重ね、並びの要素は id が同じなら差し替え、
    無ければ足す（id の無い要素は足す）。トップの remove に挙げた id の要素は、重ねた後に並びから除く。"""
    def deep(a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            return {**a, **{k: deep(a.get(k), v) if k in a else copy.deepcopy(v) for k, v in b.items()}}
        if isinstance(a, list) and isinstance(b, list):
            out = copy.deepcopy(a)
            pos = {x.get("id"): i for i, x in enumerate(out) if isinstance(x, dict) and x.get("id") is not None}
            for x in b:
                key = x.get("id") if isinstance(x, dict) else None
                if key is not None and key in pos:
                    out[pos[key]] = copy.deepcopy(x)
                else:
                    out.append(copy.deepcopy(x))
            return out
        return copy.deepcopy(b)
    frag = dict(frag or {})
    remove = set(frag.pop("remove", None) or [])
    out = deep(copy.deepcopy(raw), frag)
    if remove:
        for k, v in out.items():
            if isinstance(v, list):
                out[k] = [x for x in v if not (isinstance(x, dict) and x.get("id") in remove)]
    return out


def variant_name(path) -> str:
    return Path(path).stem


def load(path, players: int | None = None, scenario=None, variants=None) -> Definition:
    """定義を読み、案（variants。順に）とシナリオ（最後）を重ねる。"""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for v in variants or []:
        raw = overlay(raw, yaml.safe_load(Path(v).read_text(encoding="utf-8")) or {})
    if scenario:
        raw = merge(raw, yaml.safe_load(Path(scenario).read_text(encoding="utf-8")))
    return Definition(raw, players, str(path))
