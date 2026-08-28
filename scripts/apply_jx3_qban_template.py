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
import subprocess
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
# Pin CDN to a git ref so jsDelivr branch alias cache cannot serve stale icons.
# Priority: JX3_QBAN_CDN_REF env -> HEAD (if icons present) -> wechat-avatar branch.
# Workflow: commit asset changes first, re-run this script, then commit templates.
CDN_REPO = "muqing-kg/astrbot_plugin_qq_group_daily_analysis"


def _git_head_sha() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        sha = out.strip()
        return sha or None
    except Exception:
        return None


def _head_has_jx3_icons(sha: str) -> bool:
    probe = "assets/custom/jx3_qban/icons/emoji_01.webp"
    try:
        subprocess.check_output(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{sha}:{probe}"],
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def resolve_cdn_ref() -> str:
    env = os.environ.get("JX3_QBAN_CDN_REF", "").strip()
    if env:
        return env
    sha = _git_head_sha()
    if sha and _head_has_jx3_icons(sha):
        return sha
    return "wechat-avatar"


CDN_REF = resolve_cdn_ref()
CDN_BASE = (
    f"https://fastly.jsdelivr.net/gh/{CDN_REPO}@{CDN_REF}/assets/custom/jx3_qban"
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


# Curated stable set: similar framing, less crop/tear risk (no random wild poses).
# Indices are 1-based emoji_XX files under assets/custom/jx3_qban/icons/.
FIXED_EMOJI_IDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 20)


def icon_urls() -> list[str]:
    """Return the fixed curated emoji set only (no full-pool random)."""
    paths: list[Path] = []
    for i in FIXED_EMOJI_IDS:
        for ext in ("webp", "png"):
            p = ICON_DIR / f"emoji_{i:02d}.{ext}"
            if p.exists():
                paths.append(p)
                break
    if not paths:
        # fallback: first available emoji_* files
        paths = sorted(ICON_DIR.glob("emoji_*.webp")) or sorted(ICON_DIR.glob("emoji_*.png"))
    if not paths:
        av = ASSET / "quality_avatar.jpg"
        if av.exists():
            return [asset_url(av)]
        raise FileNotFoundError(ICON_DIR)
    return [asset_url(p) for p in paths]


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
    """Hard-assign curated icons to page slots (no random)."""
    if not icons:
        return text

    arr = ",\n    ".join(f'"{u}"' for u in icons)
    pool_decl = (
        "{# jx3 fixed emoji set (no random) #}\n"
        "{% set jx3_kawaii_icons = [\n    " + arr + "\n] %}\n"
    )

    # Drop legacy random bag/macro if present.
    text = re.sub(
        r"\{%\s*set\s*jx3_bag_state\s*=\s*namespace\(bags=\{\}\)\s*%\}[\s\S]*?\{%\s*endmacro\s*%\}\s*",
        "",
        text,
        count=1,
    )
    text = re.sub(
        r"\{%\s*set\s*jx3_kawaii_icons\s*=\s*\[[\s\S]*?\]\s*%\}\s*",
        "",
        text,
        count=1,
    )
    text = re.sub(
        r"\{#\s*jx3 fixed emoji set[\s\S]*?#\}\s*",
        "",
        text,
        count=1,
    )

    if "<body" in text:
        text = re.sub(r"(<body[^>]*>)", r"\1\n" + pool_decl, text, count=1, flags=re.I)
    else:
        text = pool_decl + text

    # Build-time fixed URLs for hero/section/badge slots (stable every render).
    pattern = re.compile(
        r'(<img\s+class="(hero-kawaii|section-kawaii|badge-kawaii)"\s*(?:\n\s*)?src=")[^"]*(")',
        re.S,
    )
    slot_i = 0

    def _slot_repl(m: re.Match[str]) -> str:
        nonlocal slot_i
        url = icons[slot_i % len(icons)]
        slot_i += 1
        return m.group(1) + url + m.group(3)

    text = pattern.sub(_slot_repl, text)
    # Also replace any leftover jx3_take() calls.
    text = re.sub(
        r"\{\{\s*jx3_take\([^}]*\)\s*\}\}",
        lambda _m: icons[0],
        text,
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




def ensure_emoji_align_css(text: str) -> str:
    """Match ATRI sticker framing: object-fit:cover + white chip background.

    Assets must already include transparent margin (see refill_jx3_emojis.py).
    Do not force contain/scale — that fought ATRI CSS and made cropped stickers
    look incomplete.
    """
    # Drop previous experimental override if present.
    if "jx3-emoji-align" in text:
        text = re.sub(
            r"\n?\s*/\* jx3-emoji-align \*/[\s\S]*?(?=\n\s*/\*|\n\s*</style>)",
            "\n        ",
            text,
            count=1,
        )
    # Ensure base ATRI cover rules stay cover (in case a prior patch changed them).
    text = re.sub(
        r"(\.(?:section-kawaii|hero-kawaii|badge-kawaii)\s*\{[\s\S]*?object-fit:\s*)contain(\s*!important)?",
        r"\1cover",
        text,
    )
    text = re.sub(
        r"(\.html-slot\s+\.item-emoji\s*\{[\s\S]*?object-fit:\s*)contain(\s*!important)?",
        r"\1cover",
        text,
    )
    text = re.sub(
        r"(\.quote-floating-emoji\s*\{[\s\S]*?object-fit:\s*)contain(\s*!important)?",
        r"\1cover",
        text,
    )
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


def ensure_avatar_fill_css(text: str) -> str:
    """Make user avatars fill circular frames without white letterbox gaps."""
    avatar_css = """
        .q-avatar-box {
            position: relative;
            margin-bottom: 4px;
            width: 44px;
            height: 44px;
            border-radius: 50%;
            overflow: hidden;
            flex-shrink: 0;
            border: 2px solid #fff;
            box-sizing: border-box;
            background-color: #e8eef8;
            box-shadow: 0 4px 10px rgba(91, 160, 201, 0.16);
        }

        .q-avatar {
            width: 100%;
            height: 100%;
            display: block;
            border: 0;
            border-radius: 0;
            background-color: transparent;
            object-fit: cover;
            object-position: center center;
        }

        .quote-wrapper:nth-child(odd) .q-avatar-box {
            box-shadow: 0 0 0 2px var(--sky);
        }

        .quote-wrapper:nth-child(even) .q-avatar-box {
            box-shadow: 0 0 0 2px var(--quote);
        }
"""
    # Replace the baseline ATRI avatar block (box + img + odd/even ring).
    text, n = re.subn(
        r"\n\s*\.q-avatar-box\s*\{[\s\S]*?\}\s*"
        r"\n\s*\.q-avatar\s*\{[\s\S]*?\}\s*"
        r"\n\s*\.quote-wrapper:nth-child\(odd\) \.q-avatar(?:-box)?\s*\{[\s\S]*?\}\s*"
        r"\n\s*\.quote-wrapper:nth-child\(even\) \.q-avatar(?:-box)?\s*\{[\s\S]*?\}",
        "\n" + avatar_css.rstrip() + "\n",
        text,
        count=1,
    )
    if n == 0:
        print("WARN avatar fill CSS block not found")

    # Responsive size targets the frame, not the bare img.
    text = re.sub(
        r"\.q-avatar,\s*\n\s*\.quote-floating-emoji\s*\{"
        r"\s*width:\s*34px;\s*height:\s*34px;\s*\}",
        ".q-avatar-box {\n"
        "                    width: 34px;\n"
        "                    height: 34px;\n"
        "                }\n\n"
        "                .quote-floating-emoji {\n"
        "                    width: 34px;\n"
        "                    height: 34px;\n"
        "                }",
        text,
        count=1,
    )
    text = text.replace(
        ".quote-wrapper:nth-child(odd) .q-avatar {\n"
        "            animation: avatarRing 2.8s ease-in-out infinite;\n"
        "        }\n"
        "        .quote-wrapper:nth-child(even) .q-avatar {\n"
        "            animation: avatarRingLilac 3s ease-in-out infinite;\n"
        "        }",
        ".quote-wrapper:nth-child(odd) .q-avatar-box {\n"
        "            animation: avatarRing 2.8s ease-in-out infinite;\n"
        "        }\n"
        "        .quote-wrapper:nth-child(even) .q-avatar-box {\n"
        "            animation: avatarRingLilac 3s ease-in-out infinite;\n"
        "        }",
    )
    return text


def ensure_title_avatar_markup(text: str) -> str:
    """Wrap title avatars so object-fit:cover fills the circular frame."""
    old = (
        "{% if title.avatar_data %}\n"
        '            <img src="{{ title.avatar_data }}" \n'
        '                 alt="头像" \n'
        '                 style="width: 50px; height: 50px; border-radius: 50%; '
        'object-fit: cover; border: 2px solid #667eea;">\n'
        "            {% endif %}"
    )
    new = (
        "{% if title.avatar_data %}\n"
        '            <div class="title-avatar-box" style="width: 50px; height: 50px; '
        "border-radius: 50%; overflow: hidden; flex-shrink: 0; border: 2px solid #667eea; "
        'box-sizing: border-box; background-color: #e8eef8;">\n'
        '                <img src="{{ title.avatar_data }}"\n'
        '                     alt="头像"\n'
        '                     style="width: 100%; height: 100%; object-fit: cover; '
        'object-position: center center; display: block;">\n'
        "            </div>\n"
        "            {% endif %}"
    )
    if "title-avatar-box" in text:
        return text
    if old in text:
        return text.replace(old, new, 1)
    # Loose fallback for minor whitespace drift from ATRI base.
    loose = re.compile(
        r"\{%\s*if\s+title\.avatar_data\s*%\}\s*"
        r'<img\s+src="\{\{\s*title\.avatar_data\s*\}\}"\s*'
        r'alt="头像"\s*'
        r'style="width:\s*50px;\s*height:\s*50px;[^"]*"\s*>\s*'
        r"\{%\s*endif\s*%\}",
        re.IGNORECASE,
    )
    text2, n = loose.subn(new, text, count=1)
    if n == 0:
        print("WARN title avatar markup not patched")
        return text
    return text2


def ensure_image_force_desktop_css(text: str, filename: str) -> str:
    """image_template only: T2I viewport is ~800px; keep desktop layout (no narrow stack)."""
    if filename != "image_template.html":
        return text
    css = """
        /* jx3-image-force-desktop */
        html, body {
            min-width: 980px;
        }
        .page, .inner {
            min-width: 900px;
        }
        .header {
            flex-direction: row !important;
            align-items: flex-end !important;
        }
        .header-copy {
            max-width: 64% !important;
        }
        .stats-grid {
            grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
        }
        .hero-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        }
        .token-grid,
        .title-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        }
        .hero-character,
        .peak-image,
        .deco-character {
            display: block !important;
        }
"""
    # Drop mobile breakpoints that collapse the screenshot layout.
    text = re.sub(
        r"\n\s*@media\s*\(max-width:\s*860px\)\s*\{[\s\S]*?\n\s*\}",
        "\n",
        text,
        count=1,
    )
    text = re.sub(
        r"\n\s*@media\s*\(max-width:\s*640px\)\s*\{[\s\S]*?\n\s*\}",
        "\n",
        text,
        count=1,
    )
    if "jx3-image-force-desktop" in text:
        text = re.sub(
            r"/\* jx3-image-force-desktop \*/[\s\S]*?(?=\n\s*/\*|\n\s*</style>)",
            css.strip() + "\n        ",
            text,
            count=1,
        )
        return text
    idx = text.find("</style>")
    if idx >= 0:
        text = text[:idx] + css + text[idx:]
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
    text = ensure_emoji_align_css(text)
    text = ensure_avatar_fill_css(text)
    text = ensure_image_force_desktop_css(text, path.name)
    text = fix_hero_title_break(text, path.name)
    write_text(path, text)





def replace_fragment_emojis(text: str, icons: list[str]) -> str:
    """Fragment pools use the same curated set; pick by loop index (no random)."""
    if not icons:
        return text
    arr = ",\n    ".join(f'"{u}"' for u in icons)
    for name in ("quote_emojis", "topic_emojis", "title_emojis"):
        pattern = r"\{%\s*set\s+" + re.escape(name) + r"\s*=\s*\[[\s\S]*?\]\s*%\}"
        replacement = "{% set " + name + " = [\n    " + arr + "\n] %}"
        text, n = re.subn(pattern, replacement, text, count=1)
        if n == 0:
            print(f"WARN no block for {name}")
        else:
            print(f"fixed {name} with {len(icons)} curated icons")

    # Remove legacy random bag macro
    text = re.sub(
        r"\{%\s*set\s*jx3_frag_state\s*=\s*namespace\(bags=\{\}\)\s*%\}[\s\S]*?\{%\s*endmacro\s*%\}\s*",
        "",
        text,
        count=1,
    )

    # Fixed by list position: 1st item -> icons[0], 2nd -> icons[1], ...
    fixed = {
        "quote_emojis": "{{ quote_emojis[loop.index0 % (quote_emojis|length)] }}",
        "topic_emojis": "{{ topic_emojis[loop.index0 % (topic_emojis|length)] }}",
        "title_emojis": "{{ title_emojis[loop.index0 % (title_emojis|length)] }}",
    }
    for name, expr in fixed.items():
        text = text.replace(f"{{{{ {name} | random }}}}", expr)
        text = text.replace(f"{{{{ jx3_take_from({name}, '{name.split('_')[0]}') }}}}", expr)
        # common pool_name variants used previously
        short = name.split("_")[0]
        text = text.replace(f"{{{{ jx3_take_from({name}, '{short}') }}}}", expr)
    # any remaining jx3_take_from(...)
    text = re.sub(
        r"\{\{\s*jx3_take_from\((quote_emojis|topic_emojis|title_emojis)[^}]*\)\s*\}\}",
        lambda m: fixed[m.group(1)],
        text,
    )
    return text

def patch_fragments(path: Path, icons: list[str] | None = None) -> None:
    text = brand_text_only(path.read_text(encoding="utf-8"))
    if icons:
        text = replace_fragment_emojis(text, icons)
    if path.name == "user_title_item.html":
        text = ensure_title_avatar_markup(text)
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
        print(f"cdn ref: {CDN_REF}")
        print(f"cdn base: {CDN_BASE}")
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
