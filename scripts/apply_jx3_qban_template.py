# -*- coding: utf-8 -*-
"""Build jx3_qban from clean ATRI baseline.

Lightweight by default: reference assets via CDN (or compact webp data-uri fallback),
so image_template.html stays near other templates' size instead of multi-MB base64.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "jx3_qban"
SRC = ROOT / "src" / "infrastructure" / "reporting" / "templates" / "ATRI"
DST = ROOT / "src" / "infrastructure" / "reporting" / "templates" / NAME
ASSET = ROOT / "assets" / "custom" / "jx3_qban"
SNAPSHOT = ROOT / "assets" / "custom" / "templates" / NAME
SCHEMA = ROOT / "_conf_schema.json"

# After push, T2I can fetch these like official ATRI assets.
CDN_BASE = (
    "https://fastly.jsdelivr.net/gh/muqing-kg/"
    "astrbot_plugin_qq_group_daily_analysis@wechat-avatar/"
    "assets/custom/jx3_qban"
)

# EMBED_MODE:
# - cdn: tiny HTML, needs network in T2I (recommended, ATRI-like)
# - data: compact webp/jpeg base64 (offline-safe, larger HTML)
EMBED_MODE = os.environ.get("JX3_QBAN_EMBED_MODE", "cdn").strip().lower()


def prefer(*cands: Path) -> Path:
    for c in cands:
        if c.exists():
            return c
    return cands[-1]


BIG = {
    "hero": prefer(ASSET / "hero.webp", ASSET / "hero.png"),
    "deco": prefer(ASSET / "deco.webp", ASSET / "deco.png"),
    "peak": prefer(ASSET / "peak.webp", ASSET / "peak.png"),
}
HEADER_BG = prefer(ASSET / "header_bg.jpg", ASSET / "header_bg.png")
ICON_DIR = ASSET / "icons"


def data_uri(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def asset_url(path: Path) -> str:
    rel = path.relative_to(ASSET).as_posix()
    if EMBED_MODE == "data":
        return data_uri(path)
    # default cdn
    return f"{CDN_BASE}/{rel}"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = text.encode("utf-8")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def ensure_base() -> None:
    if not SRC.is_dir():
        raise FileNotFoundError(SRC)
    for k, p in BIG.items():
        if not p.exists():
            raise FileNotFoundError(f"missing {k}: {p}")
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)


def icon_urls() -> list[str]:
    icons = sorted(ICON_DIR.glob("icon_*.webp")) + sorted(ICON_DIR.glob("emoji_*.webp"))
    if not icons:
        icons = sorted(ICON_DIR.glob("icon_*.png")) + sorted(ICON_DIR.glob("emoji_*.png"))
    if not icons:
        av = ASSET / "quality_avatar.jpg"
        if av.exists():
            return [asset_url(av)]
        raise FileNotFoundError(ICON_DIR)
    return [asset_url(p) for p in icons]


def brand_text_only(text: str) -> str:
    reps = [
        ("亚托莉的群聊观测日志", "唐小珂的群聊观澜录"),
        ("亚托莉的宝藏瓶", "唐小珂的藏宝匣"),
        ("亚托莉观测报告", "唐小珂观澜报告"),
        ("ATRI 群聊日报", "唐小珂的群聊日报"),
        ("高性能的亚托莉", "唐小珂"),
        ("高性能亚托莉", "唐小珂"),
        ("亚托莉", "唐小珂"),
        ("A.T.R.I · Daily Communication Report", "J.X.3 · Jianghu Daily Report"),
        ("ATRI | Template by Liangyu-G", "JX3 · Tang Xiaoke custom template"),
        ("ATRI Theme", "JX3 Tang Xiaoke Theme"),
        ('alt="ATRI decor"', 'alt="deco"'),
        ('alt="ATRI main"', 'alt="hero"'),
        ('alt="ATRI peak"', 'alt="peak"'),
        (
            "主人，今天群里的大家也超级精神呢！身为唐小珂，已经把所有闪闪发光的聊天记忆，像打捞海底宝藏一样全都收集好啦！",
            "今天群里的大家也超级精神呢！本刺客已经把所有闪闪发光的聊天记忆，像打捞海底宝藏一样全都收集好啦！",
        ),
        (
            "主人，今天群里的大家也超级精神呢！身为高性能的唐小珂，已经把所有闪闪发光的聊天记忆，像打捞海底宝藏一样全都收集好啦！",
            "今天群里的大家也超级精神呢！本刺客已经把所有闪闪发光的聊天记忆，像打捞海底宝藏一样全都收集好啦！",
        ),
        ("报告主人！今天一共捕获了", "今天一共捕获了"),
        ("来自高性能唐小珂的每日特别观测报告！", "来自唐小珂的每日特别观测报告！"),
        ("少侠唐小珂", "唐小珂"),
        ("少侠", ""),
        ("您", "你"),
    ]
    for a, b in reps:
        text = text.replace(a, b)
    text = text.replace("来看看今日江湖都发生了什么吧！", "来看看今天都发生了什么吧！")
    text = text.replace(
        "来看看今日<br>江湖发生了<br>什么吧！",
        "来看看<br>今天都<br>发生了<br>什么吧！",
    )
    return text


def hide_giant_watermark(text: str) -> str:
    text = text.replace('content: "ATRI";', 'content: "";')
    text = text.replace('content: "唐小珂";', 'content: "";')
    text = re.sub(
        r'(<div class="page-watermark"[^>]*>)[\s\S]*?(</div>)',
        r"\1\2",
        text,
        count=1,
    )
    return text


def replace_big_images(text: str, urls: dict[str, str]) -> str:
    text = re.sub(
        r'(<img class="deco-character"\s+src=")[^"]+(")',
        rf'\1{urls["deco"]}\2',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'(<img class="hero-character"\s*\n?\s*src=")[^"]+(")',
        rf'\1{urls["hero"]}\2',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'(<img class="peak-image"[^>]*src=")[^"]+(")',
        rf'\1{urls["peak"]}\2',
        text,
        count=1,
        flags=re.S,
    )
    return text



def replace_small_icons(text: str, icons: list[str]) -> str:
    """Use a jinja icon pool so hero/section/badge kawaii icons randomize at render time."""
    if not icons:
        return text

    arr = ",\n    ".join(f'"{u}"' for u in icons)
    pool = "{% set jx3_kawaii_icons = [\n    " + arr + "\n] %}\n"

    # inject pool once near top of body/html content (after <body> if present, else file head)
    if "jx3_kawaii_icons" not in text:
        if "<body" in text:
            text = re.sub(r"(<body[^>]*>)", r"\1\n" + pool, text, count=1, flags=re.I)
        else:
            text = pool + text
    else:
        text = re.sub(
            r"\{%\s*set\s+jx3_kawaii_icons\s*=\s*\[[\s\S]*?\]\s*%\}",
            pool.strip(),
            text,
            count=1,
        )

    # replace fixed src on kawaii icons with random pick from pool
    text = re.sub(
        r'(<img\s+class="(hero-kawaii|section-kawaii|badge-kawaii)"\s*(?:\n\s*)?src=")[^"]*(")',
        r'\1{{ jx3_kawaii_icons | random }}\3',
        text,
        flags=re.S,
    )
    return text

def replace_header_bg(text: str) -> str:
    if not HEADER_BG.exists():
        return text
    uri = asset_url(HEADER_BG)
    css = (
        "\n        /* jx3-header-bg-once */\n"
        f"        :root {{ --jx3-header-bg: url('{uri}'); }}\n"
        "        .header-bg-carousel__slide { background-image: var(--jx3-header-bg) !important; }\n"
        "        .header { background-image: var(--jx3-header-bg) !important; }\n"
    )
    if "jx3-header-bg-once" not in text:
        idx = text.find("</style>")
        if idx >= 0:
            text = text[:idx] + css + text[idx:]
    else:
        text = re.sub(
            r"(--jx3-header-bg:\s*url\(')[^']*('\))",
            rf"\1{uri}\2",
            text,
            count=1,
        )
    text = re.sub(
        r'<div class="header-bg-carousel__slide" style="background-image: url\(\'[\s\S]*?\'\);"></div>',
        '<div class="header-bg-carousel__slide"></div>',
        text,
    )
    text = text.replace(
        "{{ t2i_atri_font_mirror }}/file/1775130588385_1774881257527_bg1.webp",
        "CSSVAR_JX3_HEADER_BG",
    )
    text = text.replace("url('CSSVAR_JX3_HEADER_BG')", "var(--jx3-header-bg)")
    text = text.replace("CSSVAR_JX3_HEADER_BG", "")
    return text



def ensure_header_readable_css(text: str) -> str:
    """Improve header text contrast on pale landscape backgrounds."""
    css = """
        /* jx3-header-readable */
        .header {
            color: #16384c;
        }
        .header::before {
            background:
                linear-gradient(90deg, rgba(255, 255, 255, 0.72) 0%, rgba(255, 255, 255, 0.42) 46%, rgba(255, 255, 255, 0.08) 100%),
                linear-gradient(135deg, rgba(255, 255, 255, 0.18), rgba(255, 255, 255, 0) 55%) !important;
        }
        .header h1 {
            color: #102c3d !important;
            font-weight: 700 !important;
            text-shadow:
                0 1px 0 rgba(255, 255, 255, 0.95),
                0 2px 10px rgba(255, 255, 255, 0.45);
        }
        .header-subtitle {
            color: #17384c !important;
            text-shadow: 0 1px 0 rgba(255, 255, 255, 0.88);
            background: rgba(255, 255, 255, 0.48);
            border: 1px solid rgba(255, 255, 255, 0.72);
            border-radius: 14px;
            padding: 10px 12px;
            backdrop-filter: blur(10px);
        }
        .eyebrow {
            color: #1a4b66 !important;
            background: rgba(255, 255, 255, 0.62) !important;
            border: 1px solid rgba(255, 255, 255, 0.8) !important;
        }
        .date-box {
            color: #16384c;
            background: rgba(255, 255, 255, 0.58) !important;
            border: 1px solid rgba(255, 255, 255, 0.78) !important;
        }
        .date-box * {
            color: inherit;
        }
"""
    if "jx3-header-readable" in text:
        text = re.sub(
            r"\n\s*/\* jx3-header-readable \*/[\s\S]*?(?=\n\s*/\* |\n\s*</style>)",
            "\n" + css + "\n",
            text,
            count=1,
        )
        if "jx3-header-readable" in text:
            return text
    idx = text.find("</style>")
    if idx >= 0:
        text = text[:idx] + css + text[idx:]
    return text

def ensure_character_image_css(text: str) -> str:
    if "/* jx3-character-fit */" in text:
        return text
    css = """
        /* jx3-character-fit */
        .deco-character,
        .hero-character,
        .peak-image {
            height: auto !important;
            object-fit: contain !important;
            image-rendering: auto;
        }
        .deco-character {
            width: 380px;
            opacity: 0.92;
            filter: drop-shadow(0 18px 30px rgba(69, 152, 205, 0.18));
        }
        .hero-title {
            word-break: keep-all;
            overflow-wrap: normal;
            line-break: strict;
        }
"""
    idx = text.find("</style>")
    if idx >= 0:
        text = text[:idx] + css + text[idx:]
    return text


def fix_hero_title_break(text: str, filename: str) -> str:
    if filename == "image_template.html":
        text = re.sub(
            r'(<h2 class="hero-title">)[\s\S]*?(</h2>)',
            r"\1来看看<br>今天都<br>发生了<br>什么吧！\2",
            text,
            count=1,
        )
    else:
        text = re.sub(
            r'(<h2 class="hero-title">)[\s\S]*?(</h2>)',
            r"\1来看看今天都发生了什么吧！\2",
            text,
            count=1,
        )
    return text


def patch_main(path: Path, urls: dict[str, str], icons: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    text = brand_text_only(text)
    text = hide_giant_watermark(text)
    text = replace_big_images(text, urls)
    text = replace_small_icons(text, icons)
    text = replace_header_bg(text)
    text = ensure_character_image_css(text)
    text = ensure_header_readable_css(text)
    text = fix_hero_title_break(text, path.name)
    write_text(path, text)




def replace_fragment_emojis(text: str, icons: list[str]) -> str:
    """Replace ATRI remote emoji lists in topic/quote/title fragments with local icon set."""
    if not icons:
        return text
    arr = ",\n    ".join(f'"{u}"' for u in icons)

    def repl_block(name: str, content: str) -> str:
        pattern = r"\{%\s*set\s+" + re.escape(name) + r"\s*=\s*\[[\s\S]*?\]\s*%\}"
        replacement = "{% set " + name + " = [\n    " + arr + "\n] %}"
        new_content, n = re.subn(pattern, replacement, content, count=1)
        if n == 0:
            print(f"WARN no block for {name}")
            return content
        print(f"replaced {name} with {len(icons)} icons")
        return new_content

    text = repl_block("quote_emojis", text)
    text = repl_block("topic_emojis", text)
    text = repl_block("title_emojis", text)
    return text

def patch_fragments(path: Path, icons: list[str] | None = None) -> None:
    text = brand_text_only(path.read_text(encoding="utf-8"))
    if icons:
        text = replace_fragment_emojis(text, icons)
    write_text(path, text)

    write_text(path, text)


def ensure_schema() -> None:
    if not SCHEMA.exists():
        return
    data = json.loads(SCHEMA.read_text(encoding="utf-8"))
    options = (
        data.get("basic", {})
        .get("items", {})
        .get("report_template", {})
        .get("options")
    )
    if not isinstance(options, list):
        return
    if NAME in options:
        print("SCHEMA already has", NAME)
        return
    if "ATRI" in options:
        options.insert(options.index("ATRI") + 1, NAME)
    else:
        options.append(NAME)
    write_text(SCHEMA, json.dumps(data, ensure_ascii=False, indent=4) + "\n")
    print("SCHEMA added", NAME)


def apply() -> int:
    try:
        ensure_base()
        urls = {k: asset_url(p) for k, p in BIG.items()}
        icons = icon_urls()
        print(f"embed mode: {EMBED_MODE}")
        for name in ("html_template.html", "image_template.html"):
            patch_main(DST / name, urls, icons)
            size = (DST / name).stat().st_size
            print(f"patched {name} ({size/1024:.1f} KB)")
        for name in (
            "chat_quality_item.html",
            "topic_item.html",
            "user_title_item.html",
            "quote_item.html",
        ):
            p = DST / name
            if p.exists():
                patch_fragments(p, icons)
                print("patched", name)
        shutil.copy2(SRC / "activity_chart.html", DST / "activity_chart.html")
        print("restored activity_chart.html from ATRI")
        if SNAPSHOT.exists():
            shutil.rmtree(SNAPSHOT)
        shutil.copytree(DST, SNAPSHOT)
        ensure_schema()
        print("DONE", NAME)
        return 0
    except Exception as exc:
        print("ERROR", exc)
        return 1


if __name__ == "__main__":
    sys.exit(apply())
