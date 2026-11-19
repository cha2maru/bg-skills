"""局面を Tabletop Simulator（TTS）の Saved Object（1 つの JSON）に書き出す。

TTS は見せ方の道具で、ルールも隠れ情報も守らない（JSON を開けば全部読める）。テストプレイで部品をさわるための書き出し。
キーパーの局面（すべて見える）をそのまま置く。画像は自作の無地の表裏 2 枚だけを使い、カードの区別は名前と説明で行う。
調査：scratchpad の tts-research.md（TTS の実機では未確認の点がある）。
"""
from __future__ import annotations

import hashlib
import struct
import subprocess
import zlib
from pathlib import Path

from .definition import Definition, table_layout

SPACING_X, SPACING_Z = 7.0, 6.0  # エリアどうしの間隔（TTS の単位）
CELL = 2.6  # pos を持つ子エリアの 1 マスの大きさ
HEX = 1.5  # 六角のマスの中心から角までの長さ
SEAT_COLORS = ["White", "Red", "Blue", "Green", "Yellow", "Orange", "Purple", "Pink"]


def _guid(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:6]  # 再出力しても同じ GUID になる


def _obj(name, gid, x, z, *, nick="", desc="", gm="", rot_y=0, rot_z=0, y=1.0, scale=1.0, color=(1, 1, 1), **extra):
    return {"Name": name, "GUID": _guid(gid),
            "Transform": {"posX": round(x, 3), "posY": y, "posZ": round(z, 3), "rotX": 0, "rotY": rot_y, "rotZ": rot_z,
                          "scaleX": scale, "scaleY": scale, "scaleZ": scale},
            "Nickname": nick, "Description": desc, "GMNotes": gm,
            "ColorDiffuse": {"r": color[0], "g": color[1], "b": color[2]},
            "Locked": False, "Grid": True, "Snap": True, "IgnoreFoW": False, "Autoraise": True, "Sticky": True,
            "Tooltip": True, "HideWhenFaceDown": True, "Hands": True,
            "LuaScript": "", "LuaScriptState": "", "XmlUI": "", **extra}


def png(path: Path, rgb):
    """単色の小さな PNG を書く（依存なし）。"""
    w, h = 64, 90
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)

    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def windows_path(p: Path) -> str:
    """TTS（Windows）から読めるパス。WSL なら wslpath -w、それ以外はそのまま。"""
    try:
        return subprocess.run(["wslpath", "-w", str(p.resolve())], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return str(p.resolve())


def _layout(d: Definition):
    """エリアの座標。根のエリアは 4 列の格子、pos を持つ子は親の原点からの位置、持たない子は横に並べる。"""
    where, i = {}, 0

    def place(areas, ox, oz, hexes=False):
        for k, a in enumerate(areas or []):
            if hexes:  # 六角の盤：アキシャル座標から互い違いの位置（マスの中心どうしの距離が等しい）
                q, r = a["pos"]
                x, z = ox + HEX * 3 ** 0.5 * (q + r / 2), oz - HEX * 1.5 * r
            elif "pos" in a:
                x, z = ox + a["pos"][0] * CELL, oz - a["pos"][1] * CELL
            else:
                x, z = ox + k * SPACING_X * 0.5, oz
            where[a["id"]] = (x, z)
            place(a.get("areas"), x, z - (0 if all("pos" in c for c in a.get("areas") or []) else SPACING_Z * 0.6), bool(a.get("hex")))

    tl = table_layout(d)
    anchor = {}
    if tl:  # 卓の配置：中央に横並び、席は中央から外へ（手前 −z、対面 +z、左 −x、右 +x）
        for k, aid in enumerate(tl["center"]):
            anchor[aid] = ((k - (len(tl["center"]) - 1) / 2) * SPACING_X, 0.0)
        out = {"bottom": (0, -1), "top": (0, 1), "left": (-1, 0), "right": (1, 0)}
        for p, ids in tl["per_player"].items():
            dx, dz = out.get(tl["seats"][p], (0, -1))
            for k, aid in enumerate(ids):
                anchor[aid] = (dx * (2 + k) * SPACING_X, dz * (1.6 + k) * SPACING_Z)
    for a in d.data["areas"]:
        if a["id"] in anchor:
            x, z = anchor[a["id"]]
        else:
            x, z = (i % 4) * SPACING_X, -(3 + i // 4) * SPACING_Z  # 卓の外は手前の下に並べる
            i += 1
        where[a["id"]] = (x, z)
        place(a.get("areas"), x, z, bool(a.get("hex")))
    return where


def _ordered(d, aid):
    a = d.areas[aid]
    return bool(a.get("ordered") or any(d.kinds[k].get("ordered") for k in d.kind_chain(a.get("kind"))))


def to_tts(d: Definition, state: dict, face_url: str, back_url: str, seats: dict | None = None) -> dict:
    deck = {"FaceURL": face_url, "BackURL": back_url, "NumWidth": 1, "NumHeight": 1, "BackIsHidden": True, "UniqueBack": False}
    colors = dict(zip(d.players, SEAT_COLORS))
    where, objs, n_card = _layout(d), [], [0]

    def card(oid, x, z, y=1.2):
        n_card[0] += 1
        st = state["states"].get(oid, {})
        attrs = d.parts[oid].get("attributes") or {}
        title = attrs.get("title") or attrs.get("name") or oid
        desc = "\n".join(filter(None, [d.text_of(oid), ", ".join(f"{k}={v}" for k, v in st.items()),
                                        ", ".join(f"{k}: {v}" for k, v in attrs.items() if k not in ("title", "name"))]))
        att = state["attached"].get(oid)
        if att:
            desc += f"\n付き先：{att['to']}"
        cid = 100 * n_card[0]
        disp = d.display(d.kind_of(oid), st)  # 状態の表示方法（SPC-038）
        c = _obj("Card", oid, x, z, y=y, nick=f"{title}", desc=desc, gm=oid,
                 rot_z=180 if disp["face"] == "down" else 0, rot_y=disp["rotate"],
                 CardID=cid, CustomDeck={str(n_card[0]): deck}, Tags=d.kind_chain(d.parts[oid].get("kind")))
        stacked = state["places"].get(oid) or []
        return [c] + [x for k, o in enumerate(stacked) for x in item(o, x + 0.4 * (k + 1), z - 0.4 * (k + 1), y + 0.3 * (k + 1))]

    def item(o, x, z, y=1.2):
        if isinstance(o, str):
            return card(o, x, z, y)
        (part, n), = o.items()
        name = d.text_of(part) or part
        if n == "unlimited":
            return [_obj("Infinite_Bag", f"bag:{part}", x, z, y=y, nick=f"{part}（無限）", desc=name, gm=part,
                         ContainedObjects=[_obj("BlockSquare", f"{part}#0", 0, 0, nick=part, desc=name, gm=part, scale=0.4)])]
        return [_obj("BlockSquare", f"{part}@{x},{z}#{j}", x + 0.5 * j, z, y=y + 0.2, nick=part, desc=name, gm=part,
                     scale=0.4, color=(0.9, 0.3, 0.2)) for j in range(n)]

    for aid, a in d.areas.items():
        x, z = where[aid]
        owner = a.get("owner")
        objs.append(_obj("BlockSquare", "area:" + aid, x, z, y=0.6, scale=1.0, nick=a.get("name") or aid,
                         desc=d.text_of(aid) or "", gm="area:" + aid, Locked=True, color=(0.75, 0.8, 0.75)))
        face = (a.get("visibility") or {}).get("face")
        out_z = 2.5 if z > 0 else -2.5  # 手札ゾーンは席の外側（対面なら奥）に置き、持ち主の方を向ける
        if owner in colors and face == "owner":  # 手札：持ち主の色の手札ゾーン
            objs.append(_obj("HandTrigger", "hand:" + aid, x, z + out_z, y=2.0, nick=a.get("name") or aid,
                             rot_y=180 if z > 0 else 0, FogColor=colors[owner]))
        items = state["places"].get(aid, [])
        cards = [o for o in items if isinstance(o, str)]
        if _ordered(d, aid) and len(cards) > 1:
            built = [card(o, x, z)[0] for o in cards]
            # shortcut: TTS の ContainedObjects は先頭を山の上として並べる（実機で未確認。逆なら reversed を外す）
            built = list(reversed(built))
            objs.append(_obj("Deck", "deck:" + aid, x, z, y=1.2, nick=a.get("name") or aid, gm="area:" + aid,
                             rot_z=built[0]["Transform"]["rotZ"], DeckIDs=[c["CardID"] for c in built],
                             CustomDeck={k: v for c in built for k, v in c["CustomDeck"].items()}, ContainedObjects=built))
        else:
            dz = out_z if owner in colors and face == "owner" else 0
            for k, o in enumerate(cards):
                objs += card(o, x + 0.9 * k - 0.45 * (len(cards) - 1), z + dz)
        for o in items:
            if isinstance(o, dict):
                objs += item(o, x + 2.5, z)
    rules = "\n\n".join(f"[{r['id']}] {r['text']}" for r in d.data.get("rules") or [])
    g = d.data["game"]
    return {"SaveName": f"{g.get('name') or g['id']}（版 {g.get('version')}）", "GameMode": "", "Date": "",
            "Gravity": 0.5, "PlayArea": 0.5, "Table": "", "Sky": "", "Note": g.get("summary", ""), "Rules": rules,
            "LuaScript": "", "LuaScriptState": "", "XmlUI": "", "TabStates": {}, "VersionNumber": "",
            "ObjectStates": objs}


def export(d: Definition, state: dict, out: Path, seats: dict | None = None) -> dict:
    """out に JSON と、同じ名前のサムネイル、表裏の画像を書く。"""
    import json
    out.parent.mkdir(parents=True, exist_ok=True)
    face, back = out.with_name(out.stem + "-face.png"), out.with_name(out.stem + "-back.png")
    png(face, (245, 242, 232))
    png(back, (91, 70, 48))
    png(out.with_suffix(".png"), (47, 93, 71))  # Saved Objects の一覧に出るサムネイル
    data = to_tts(d, state, windows_path(face), windows_path(back), seats)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data
