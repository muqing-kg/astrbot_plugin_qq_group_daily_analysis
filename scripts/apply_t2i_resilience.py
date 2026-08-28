# -*- coding: utf-8 -*-
"""Re-apply T2I resilience after upstream reset (auto-sync maintenance).

Survives `reset --hard upstream/main` because auto-sync re-runs this script.
Idempotent: safe on already-patched trees.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATORS = ROOT / "src" / "infrastructure" / "reporting" / "generators.py"
SCHEMA = ROOT / "_conf_schema.json"
MARKER = "WECHATBRIDGE_T2I_RESILIENCE_V1"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = text.encode("utf-8")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
    tmp.replace(path)


def patch_schema() -> None:
    if not SCHEMA.exists():
        print("SCHEMA missing, skip", SCHEMA)
        return
    data = json.loads(SCHEMA.read_text(encoding="utf-8"))
    changed = False

    def walk(obj):
        nonlocal changed
        if isinstance(obj, dict):
            if "t2i_r1_device_scale" in obj and isinstance(
                obj["t2i_r1_device_scale"], dict
            ):
                node = obj["t2i_r1_device_scale"]
                if node.get("default") != "high":
                    node["default"] = "high"
                    changed = True
                hint = (
                    "影响图片清晰度。normal=1.0x, high=1.3x, ultra=1.8x。"
                    "ultra 在公共 T2I 上更容易 500/内存不足，默认 high 更稳；"
                    "自建高配 T2I 可改回 ultra。"
                )
                if node.get("hint") != hint:
                    node["hint"] = hint
                    changed = True
            if "t2i_r1_timeout" in obj and isinstance(obj["t2i_r1_timeout"], dict):
                if obj["t2i_r1_timeout"].get("default") != 90000:
                    obj["t2i_r1_timeout"]["default"] = 90000
                    changed = True
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    if changed:
        write_text(SCHEMA, json.dumps(data, ensure_ascii=False, indent=4) + "\n")
        print("SCHEMA t2i defaults -> high / 90000")
    else:
        print("SCHEMA t2i defaults already set")


def strategy_block() -> str:
    # Not an f-string for the body: avoid re.sub / escape footguns.
    return (
        f"# 用户配置的两轮策略 + 服务端 500/过载时的轻量兜底 ({MARKER})\n"
        "            render_strategies = list(\n"
        "                self.config_manager.get_t2i_rendering_strategies()\n"
        "            )\n"
        "            render_strategies.extend(self._get_emergency_t2i_strategies())\n"
        "\n"
        "            # 使用信号量控制并发进入渲染引擎\n"
        "            async with self._render_semaphore:\n"
        '                logger.debug(f"[T2I] 已进入渲染队列 (群: {group_id})")\n'
        "                logger.info(\n"
        '                    f"[T2I] HTML 长度 {len(html_content)} 字符，"\n'
        '                    f"将尝试 {len(render_strategies)} 轮渲染"\n'
        "                )\n"
        "\n"
        "                last_exception = None\n"
        "                last_error_hint = None\n"
        "\n"
        "                for attempt, image_options in enumerate(render_strategies, 1):\n"
        "                    try:\n"
        "                        # 勿污染配置 dict：每轮使用副本\n"
        "                        options = dict(image_options)\n"
        '                        if options.get("type") == "png":\n'
        '                            options.pop("quality", None)\n'
        "\n"
        '                        logger.info(f"正在尝试第 {attempt} 轮渲染策略: {options}")\n'
        "\n"
        "                        # 改为获取 bytes 数据，避免 OneBot 无法访问内部 URL\n"
        "                        image_data = await html_render_func(\n"
        "                            html_content,  # 渲染后的HTML内容\n"
        "                            {},  # 空数据字典，因为数据已包含在HTML中\n"
        "                            False,  # return_url=False，直接获取图片数据\n"
        "                            options,\n"
        "                        )\n"
        "\n"
        "                        if image_data:\n"
        "                            # 校验是否为合法图片（防止 T2I 返回 500 错误 HTML/纯文本）\n"
        "                            is_valid = False\n"
        "                            actual_data_head = None\n"
        "                            payload_for_error: bytes | None = None\n"
        "\n"
        "                            if isinstance(image_data, bytes):\n"
        "                                actual_data_head = image_data[:10]\n"
        "                                payload_for_error = image_data[:4096]\n"
        "                            elif isinstance(image_data, str) and os.path.exists(\n"
        "                                image_data\n"
        "                            ):\n"
        "                                try:\n"
        '                                    with open(image_data, "rb") as f:\n'
        "                                        payload_for_error = f.read(4096)\n"
        "                                        actual_data_head = payload_for_error[:10]\n"
        "                                except Exception as e:\n"
        '                                    logger.warning(f"读取图片临时文件失败: {e}")\n'
        "\n"
        "                            if actual_data_head:\n"
        "                                # 检查 magic numbers (JPEG: FF D8, PNG: 89 50 4E 47)\n"
        "                                if actual_data_head.startswith(\n"
        '                                    b"\\xff\\xd8"\n'
        "                                ) or actual_data_head.startswith(b\"\\x89PNG\"):\n"
        "                                    is_valid = True\n"
        "                                else:\n"
        "                                    render_error = None\n"
        "                                    if payload_for_error:\n"
        "                                        render_error = (\n"
        "                                            self._extract_render_error_summary(\n"
        "                                                payload_for_error\n"
        "                                            )\n"
        "                                        )\n"
        "                                    if render_error:\n"
        "                                        last_error_hint = render_error\n"
        "                                        logger.warning(\n"
        '                                            f"[T2I] 渲染引擎返回了错误而非图片: {render_error}"\n'
        "                                        )\n"
        "                                    else:\n"
        '                                        text_preview = ""\n'
        "                                        try:\n"
        "                                            text_preview = actual_data_head.decode(\n"
        '                                                "utf-8", errors="replace"\n'
        "                                            )\n"
        "                                        except Exception:\n"
        '                                            text_preview = ""\n'
        "                                        last_error_hint = (\n"
        '                                            f"非图片数据 head_hex={actual_data_head.hex()}"\n'
        "                                            + (\n"
        '                                                f" text={text_preview!r}"\n'
        "                                                if text_preview.strip()\n"
        '                                                else ""\n'
        "                                            )\n"
        "                                        )\n"
        "                                        logger.warning(\n"
        '                                            f"渲染结果似乎不是有效的图片数据"\n'
        '                                            f" (头部: {actual_data_head.hex()}"\n'
        "                                            + (\n"
        '                                                f", 文本: {text_preview!r}"\n'
        "                                                if text_preview.strip()\n"
        '                                                else ""\n'
        "                                            )\n"
        '                                            + ")"\n'
        "                                        )\n"
        "\n"
        "                            if is_valid:\n"
        "                                if isinstance(image_data, bytes):\n"
        '                                    b64 = base64.b64encode(image_data).decode("utf-8")\n'
        '                                    image_url = f"base64://{b64}"\n'
        "                                    logger.info(\n"
        '                                        f"图片生成成功 (轮次 {attempt}): [Base64 Data {len(image_data)} bytes]"\n'
        "                                    )\n"
        "                                    return image_url, html_content\n"
        "                                elif isinstance(image_data, str):\n"
        "                                    logger.info(\n"
        '                                        f"图片生成成功 (轮次 {attempt}): {image_data}"\n'
        "                                    )\n"
        "                                    return image_data, html_content\n"
        "\n"
        "                        logger.warning(\n"
        '                            f"渲染轮次 {attempt} ({options.get(\'type\')}) 返回了无效或空数据"\n'
        "                        )\n"
        "\n"
        "                    except Exception as e:\n"
        '                        logger.warning(f"渲染轮次 {attempt} 失败: {e}")\n'
        "                        last_exception = e\n"
        "                        last_error_hint = str(e)\n"
        "                        if attempt < len(render_strategies):\n"
        '                            logger.info("准备尝试下一轮回退策略")\n'
        "                        continue\n"
        "\n"
        "                # 如果所有策略都失败\n"
        "                logger.error(\n"
        '                    f"所有渲染尝试都失败。最后一个错误: {last_exception}；"\n'
        '                    f"最近非图片响应: {last_error_hint}。"\n'
        '                    f"常见原因：AstrBot T2I 端点 500/过载、超时过短、分辨率 ultra 内存不足、"\n'
        '                    f"HTML 过大或外链资源拉取失败。请加大 t2i 超时、降低 device_scale，"\n'
        '                    f"或更换/自建 T2I 服务。"\n'
        "                )\n"
        "                return None, html_content\n"
    )


def helpers_block() -> str:
    return f"""
    # --- {MARKER} start ---
    @staticmethod
    def _get_emergency_t2i_strategies() -> list[dict]:
        \"\"\"用户策略失败后的轻量兜底（降低分辨率/改 JPEG，拉长超时）。\"\"\"
        return [
            {{
                "full_page": True,
                "type": "jpeg",
                "quality": 75,
                "device_scale_factor_level": "normal",
                "timeout": 120000,
                "_emergency": True,
            }},
            {{
                "full_page": True,
                "type": "jpeg",
                "quality": 60,
                "device_scale_factor_level": "normal",
                "timeout": 180000,
                "_emergency": True,
            }},
        ]

    def _extract_html_error_summary(self, data: bytes) -> str | None:
        \"\"\"兼容旧调用名；实际走统一的渲染错误摘要。\"\"\"
        return self._extract_render_error_summary(data)

    def _extract_render_error_summary(self, data: bytes) -> str | None:
        \"\"\"从 T2I 返回的非图片字节流中提取可读错误（HTML 页或纯文本 500）。\"\"\"
        try:
            if not data:
                return None
            if data.startswith(b"\\x89PNG") or data.startswith(b"\\xff\\xd8"):
                return None

            content = data.decode("utf-8", errors="ignore").strip()
            if not content:
                return None

            sample = content[:240]
            printable_ratio = sum(
                1 for c in sample if c.isprintable() or c.isspace()
            ) / max(len(sample), 1)
            if printable_ratio < 0.85:
                return None

            content_lower = content.lower()
            if "<html" in content_lower or "<!doctype html" in content_lower:
                title_match = re.search(
                    r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL
                )
                if title_match:
                    return f"HTML 错误页: {{title_match.group(1).strip()}}"

                h1_match = re.search(
                    r"<h1>(.*?)</h1>", content, re.IGNORECASE | re.DOTALL
                )
                if h1_match:
                    return f"HTML 错误页: {{h1_match.group(1).strip()}}"

                return f"HTML 响应 (前100字): {{content[:100].strip()}}..."

            first_line = content.splitlines()[0].strip() if content else ""
            known = (
                "internal server error",
                "bad gateway",
                "service unavailable",
                "gateway timeout",
                "error",
            )
            if any(k in content_lower for k in known) or first_line:
                preview = first_line[:180] or content[:180]
                return f"文本错误响应: {{preview}}"
        except Exception:
            pass
        return None
    # --- {MARKER} end ---
"""


def patch_generators() -> None:
    if not GENERATORS.exists():
        raise FileNotFoundError(GENERATORS)
    text = GENERATORS.read_text(encoding="utf-8")

    # Strip previous helper block if present
    text = re.sub(
        rf"\n    # --- {re.escape(MARKER)} start ---.*?# --- {re.escape(MARKER)} end ---\n?",
        "\n",
        text,
        count=1,
        flags=re.S,
    )

    pat = re.compile(
        r"(?:#[^\n]*\n\s*)?render_strategies = (?:list\(\s*)?self\.config_manager\.get_t2i_rendering_strategies\(\)(?:\s*\))?"
        r"(?:\s*\n\s*render_strategies\.extend\(self\._get_emergency_t2i_strategies\(\)\))?"
        r"[\s\S]*?"
        r"return None, html_content\n\n        except Exception as e:\n"
        r"            logger\.error\(f\"生成图片报告过程发生严重错误",
        re.M,
    )
    m = pat.search(text)
    if not m:
        raise RuntimeError(
            "cannot locate T2I strategy loop in generators.py — upstream changed too much"
        )

    # Use callable replacement so backslashes are literal (re.sub string rules).
    def _repl(_m: re.Match[str]) -> str:
        return (
            strategy_block()
            + "\n        except Exception as e:\n"
            + '            logger.error(f"生成图片报告过程发生严重错误'
        )

    text = pat.sub(_repl, text, count=1)
    print("GENERATORS strategy loop patched")

    # Remove old helper defs that we will re-inject
    text = re.sub(
        r"\n    def _extract_html_error_summary\(self, data: bytes\) -> str \| None:[\s\S]*?"
        r"(?=\n    def |\n    @staticmethod|\nclass |\Z)",
        "\n",
        text,
        count=1,
    )
    text = re.sub(
        r"\n    @staticmethod\n    def _get_emergency_t2i_strategies\(\)[\s\S]*?"
        r"(?=\n    def |\n    @staticmethod|\nclass |\Z)",
        "\n",
        text,
        count=1,
    )
    text = re.sub(
        r"\n    def _extract_render_error_summary\(self, data: bytes\) -> str \| None:[\s\S]*?"
        r"(?=\n    def |\n    @staticmethod|\nclass |\Z)",
        "\n",
        text,
        count=1,
    )

    helpers = helpers_block()
    if "async def close(self)" in text:
        idx = text.rfind("    async def close(self)")
        text = text[:idx] + helpers + "\n" + text[idx:]
    else:
        text = text.rstrip() + "\n" + helpers + "\n"
    print("GENERATORS helpers injected")

    # syntax check
    compile(text, str(GENERATORS), "exec")
    write_text(GENERATORS, text)


def main() -> int:
    try:
        patch_schema()
        patch_generators()
        print("DONE t2i resilience")
        return 0
    except Exception as e:
        print(f"FAIL t2i resilience: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
