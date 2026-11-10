#!/usr/bin/env python3
"""Build the Orca "Pokémon Pets" plugin: embed PMD SpriteCollab sheets as data URLs into one panel.html.

Orca plugin panels are a single sandboxed HTML document (CSP: inline script/style, img-src data: only),
so every sprite sheet is inlined. Output goes to ../plugin/pokemon-pets (the Orca dev plugin path).
"""
import base64
import json
import os
import struct
import xml.etree.ElementTree as ET
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SPRITES = os.path.join(HERE, "sprites")
OUT = os.path.join(os.path.dirname(HERE), "plugin", "pokemon-pets")

ROSTER = [
    ("0025", "pikachu", "Pikachu"),
    ("0001", "bulbasaur", "Bulbasaur"),
    ("0004", "charmander", "Charmander"),
    ("0007", "squirtle", "Squirtle"),
    ("0133", "eevee", "Eevee"),
    ("0094", "gengar", "Gengar"),
    ("0039", "jigglypuff", "Jigglypuff"),
    ("0052", "meowth", "Meowth"),
    ("0054", "psyduck", "Psyduck"),
    ("0143", "snorlax", "Snorlax"),
    ("0151", "mew", "Mew"),
    ("0175", "togepi", "Togepi"),
]
ANIMS = {"walk": "Walk", "idle": "Idle", "sleep": "Sleep", "hop": "Hop", "eat": "Eat"}
# The panel only ever shows these facing you (the sheet's first row), so the other seven
# directions are cut at build time; hop sheets alone were half the panel's weight.
FRONT_ONLY = {"hop", "eat"}
SHADOW = {"0": 0.7, "1": 1.0, "2": 1.4}

MANIFEST = {
    "manifestVersion": 1,
    "id": "pokemon-pets",
    "publisher": "luthfi",
    "name": "Pokémon Pets",
    "version": "1.3.1",
    "description": "Pokémon wander around an Orca sidebar panel and every so often get to work, each with its own kit: a little PC for coding, the Pokédex for research, a Pokémon Center machine for tests, an anvil for builds and a letter for deploys. Pick a berry from the tree and bring it to a Pokémon to feed it; press and rub one to pet it. Click one to say hi; at night they sleep.",
    "author": {"name": "Luthfi"},
    "engines": {"orca": ">=1.4.0"},
    "pluginApi": 1,
    "contributes": {
        "panels": [{"id": "pets", "title": "Pokémon", "icon": "paw-print", "entry": "panel.html"}]
    },
}


def data_url(png):
    return "data:image/png;base64," + base64.b64encode(png).decode()


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def top_rows(png, height):
    """The PNG cut down to its top `height` pixel rows. PNG filters only look at the row above,
    so the first rows of the filtered stream are valid as they are: no need to re-filter."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pos, ihdr, idat, keep = 8, None, b"", []
    while pos < len(png):
        size, kind = struct.unpack(">I4s", png[pos:pos + 8])
        data = png[pos + 8:pos + 8 + size]
        pos += 12 + size
        if kind == b"IHDR":
            ihdr = data
        elif kind == b"IDAT":
            idat += data
        elif kind in (b"PLTE", b"tRNS"):
            keep.append((kind, data))
    w, h, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", ihdr)
    assert depth == 8 and color == 6 and not interlace, "expects 8-bit RGBA, not interlaced"
    if height >= h:
        return png
    rows = zlib.decompress(idat)[:height * (1 + w * 4)]
    out = png[:8] + png_chunk(b"IHDR", struct.pack(">II", w, height) + ihdr[8:])
    for kind, data in keep:
        out += png_chunk(kind, data)
    return out + png_chunk(b"IDAT", zlib.compress(rows, 9)) + png_chunk(b"IEND", b"")


def anim_table(dex):
    root = ET.parse(os.path.join(SPRITES, dex, "AnimData.xml")).getroot()
    table = {a.findtext("Name"): a for a in root.iter("Anim")}
    return root, table


def resolve(table, name):
    seen = set()
    while name in table and table[name].findtext("CopyOf") and name not in seen:
        seen.add(name)
        name = table[name].findtext("CopyOf")
    return name if name in table else None


def build_mon(dex):
    root, table = anim_table(dex)
    anims = {}
    for key, name in ANIMS.items():
        real = resolve(table, name)
        png = os.path.join(SPRITES, dex, f"{real}-Anim.png") if real else None
        if not real or not os.path.exists(png):
            if key in ("walk", "idle"):
                raise SystemExit(f"{dex}: missing required {name} animation")
            continue
        a = table[real]
        fh = int(a.findtext("FrameHeight"))
        with open(png, "rb") as f:
            sheet = f.read()
        anims[key] = {
            "src": data_url(top_rows(sheet, fh) if key in FRONT_ONLY else sheet),
            "fw": int(a.findtext("FrameWidth")),
            "fh": fh,
            "dur": [int(d.text) for d in a.iter("Duration")],
        }
    return anims, SHADOW.get(root.findtext("ShadowSize") or "1", 1.0)


def main():
    os.makedirs(OUT, exist_ok=True)
    mons, credits = {}, []
    for dex, key, name in ROSTER:
        anims, shadow = build_mon(dex)
        mons[key] = {"name": name, "shadow": shadow, "anims": anims}
        with open(os.path.join(SPRITES, dex, "credits.txt")) as f:
            authors = sorted({line.split("\t")[1] for line in f if line.count("\t") >= 2})
        credits.append(f"- {name} (#{dex}): {', '.join(authors)}")

    with open(os.path.join(HERE, "panel.template.html")) as f:
        template = f.read()
    marker = "/*__SPRITES__*/null"
    assert template.count(marker) == 1
    html = template.replace(marker, json.dumps({"mons": mons}, separators=(",", ":")))
    with open(os.path.join(OUT, "panel.html"), "w") as f:
        f.write(html)
    with open(os.path.join(OUT, "orca-plugin.json"), "w") as f:
        json.dump(MANIFEST, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(OUT, "CREDITS.md"), "w") as f:
        f.write(
            "# Credits\n\nSprites from the PMD Sprite Repository (SpriteCollab), "
            "https://github.com/PMDCollab/SpriteCollab — licensed CC BY-NC 4.0.\n"
            "Pokémon © Nintendo / Creatures Inc. / GAME FREAK inc. Personal, non-commercial use.\n\n"
            "Sprite authors:\n" + "\n".join(credits) + "\n"
        )
    print(f"panel.html {os.path.getsize(os.path.join(OUT, 'panel.html')) / 1024:.0f} KB, {len(mons)} Pokémon -> {OUT}")


if __name__ == "__main__":
    main()
