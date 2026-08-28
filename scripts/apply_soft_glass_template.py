from __future__ import annotations

import base64
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_NAME = "soft_glass"
SRC_SNAPSHOT = ROOT / "assets" / "custom" / "templates" / TEMPLATE_NAME
DST_TEMPLATE = ROOT / "src" / "infrastructure" / "reporting" / "templates" / TEMPLATE_NAME
CHARACTER = ROOT / "assets" / "custom" / "soft_glass_character.jpg"
# backward-compatible fallback
CHARACTER_FALLBACK = ROOT / "assets" / "custom" / "scrapbook_character.jpg"
SCHEMA = ROOT / "_conf_schema.json"
CHAT_QUALITY = DST_TEMPLATE / "chat_quality_item.html"


def _copy_template() -> None:
    if not SRC_SNAPSHOT.is_dir():
        raise FileNotFoundError(f"missing snapshot: {SRC_SNAPSHOT}")
    if DST_TEMPLATE.exists():
        shutil.rmtree(DST_TEMPLATE)
    shutil.copytree(SRC_SNAPSHOT, DST_TEMPLATE)
    print(f"COPIED {SRC_SNAPSHOT} -> {DST_TEMPLATE}")


def _embed_character() -> None:
    img = CHARACTER if CHARACTER.exists() else CHARACTER_FALLBACK
    if not img.exists():
        raise FileNotFoundError(f"missing character image: {CHARACTER}")
    if not CHAT_QUALITY.exists():
        raise FileNotFoundError(f"missing {CHAT_QUALITY}")

    data = img.read_bytes()
    mime = "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif data[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    b64 = base64.b64encode(data).decode("ascii")
    new_src = f"data:{mime};base64,{b64}"

    text = CHAT_QUALITY.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(<img class="character-img"\s*\n?\s*src=")data:image/[^;]+;base64,[^"]+(")',
        re.DOTALL,
    )
    if not pattern.search(text):
        pattern = re.compile(
            r'(class="character-img"[^>]*src=")data:image/[^"]+(")',
            re.DOTALL,
        )
    if not pattern.search(text):
        raise RuntimeError("character-img not found in chat_quality_item.html")

    text = pattern.sub(rf"\1{new_src}\2", text, count=1)
    for old, new in (
        (
            "<!-- TODO: 请在这里替换为你自己的 base64 图片字符串 -->",
            "<!-- 自定义角色图：assets/custom/soft_glass_character.jpg -->",
        ),
        (
            "<!-- 自定义角色图：熊猫头像（主人指定） -->",
            "<!-- 自定义角色图：assets/custom/soft_glass_character.jpg -->",
        ),
        (
            "<!-- 自定义角色图：assets/custom/scrapbook_character.jpg -->",
            "<!-- 自定义角色图：assets/custom/soft_glass_character.jpg -->",
        ),
    ):
        text = text.replace(old, new, 1)

    CHAT_QUALITY.write_text(text, encoding="utf-8")
    print(f"APPLIED character from {img.name}")


def _ensure_schema_option() -> None:
    if not SCHEMA.exists():
        print("WARN schema missing, skip")
        return
    raw = SCHEMA.read_text(encoding="utf-8")
    data = json.loads(raw)
    options = (
        data.get("basic", {})
        .get("items", {})
        .get("report_template", {})
        .get("options")
    )
    if not isinstance(options, list):
        print("WARN report_template.options not found, skip")
        return
    if TEMPLATE_NAME in options:
        print(f"SCHEMA already has {TEMPLATE_NAME}")
        return
    # keep near scrapbook if present
    if "scrapbook" in options:
        idx = options.index("scrapbook") + 1
        options.insert(idx, TEMPLATE_NAME)
    else:
        options.append(TEMPLATE_NAME)
    SCHEMA.write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    print(f"SCHEMA added option {TEMPLATE_NAME}")


def apply() -> int:
    try:
        _copy_template()
        _embed_character()
        _ensure_schema_option()
    except Exception as exc:
        print(f"ERROR {exc}")
        return 1
    print(f"DONE custom template: {TEMPLATE_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(apply())
