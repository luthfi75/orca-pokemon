#!/usr/bin/env python3
"""Build the Orca "Pokémon Pets" plugin: embed PMD SpriteCollab sheets as data URLs into one panel.html.

Orca plugin panels are a single sandboxed HTML document (CSP: inline script/style, img-src data: only),
so every sprite sheet is inlined. Output goes to ../plugin/pokemon-pets (the Orca dev plugin path).
"""
import base64
import json
import os
import xml.etree.ElementTree as ET

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
SHADOW = {"0": 0.7, "1": 1.0, "2": 1.4}

MANIFEST = {
    "manifestVersion": 1,
    "id": "pokemon-pets",
    "publisher": "luthfi",
    "name": "Pokémon Pets",
    "version": "1.2.0",
    "description": "Pokémon wander around an Orca sidebar panel and every so often get to work, each with its own kit: a little PC for coding, the Pokédex for research, a Pokémon Center machine for tests, an anvil for builds and a letter for deploys. Pick a berry from the tree and bring it to a Pokémon to feed it; press and rub one to pet it. Click one to say hi; at night they sleep.",
    "author": {"name": "Luthfi"},
    "engines": {"orca": ">=1.4.0"},
    "pluginApi": 1,
    "contributes": {
        "panels": [{"id": "pets", "title": "Pokémon", "icon": "paw-print", "entry": "panel.html"}]
    },
}


def data_url(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


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
        anims[key] = {
            "src": data_url(png),
            "fw": int(a.findtext("FrameWidth")),
            "fh": int(a.findtext("FrameHeight")),
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
