from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "infrastructure" / "platform" / "adapters" / "onebot_adapter.py"

CACHE_LINE = "        self._avatar_url_cache: dict[str, str] = {}\n"
MARKER = "WECHATBRIDGE_AVATAR_PATCH_V1"

HELPERS_AND_METHOD = f'''
    # --- {MARKER} start ---
    @staticmethod
    def _is_qq_cdn_avatar_url(url: str) -> bool:
        """QQ 官方 CDN 地址在微信映射 ID 上通常只会得到默认企鹅头像。"""
        lowered = str(url or "").lower()
        return (
            "q1.qlogo.cn" in lowered
            or "q2.qlogo.cn" in lowered
            or "q.qlogo.cn/headimg" in lowered
            or "p.qlogo.cn/gh/" in lowered
        )

    @staticmethod
    def _extract_avatar_url(payload: Any) -> str | None:
        """从 OneBot 用户/成员资料里提取可用头像 URL。"""
        if not isinstance(payload, dict):
            return None
        for key in (
            "avatar_url",
            "avatar",
            "wx_avatar_url",
            "headimgurl",
            "head_img",
            "headimg",
            "user_avatar",
        ):
            value = payload.get(key)
            if not isinstance(value, str):
                continue
            text = value.strip()
            if text.startswith(("http://", "https://", "data:")):
                return text
        return None

    async def _fetch_avatar_url_from_protocol(self, user_id: str) -> str | None:
        """
        优先从协议端资料接口取真实头像。

        兼容 WeChatBridge：
        - get_stranger_info / get_user_info 返回 wx.qlogo 的 avatar / avatar_url
        """
        if not hasattr(self.bot, "call_action"):
            return None

        uid_text = str(user_id).strip()
        if uid_text.lstrip("-").isdigit():
            try:
                uid_param: int | str = int(uid_text)
            except ValueError:
                uid_param = uid_text
        else:
            uid_param = uid_text

        for action_name in ("get_stranger_info", "get_user_info"):
            try:
                result = await asyncio.wait_for(
                    self.bot.call_action(action_name, user_id=uid_param),
                    timeout=1.5,
                )
            except Exception as exc:
                logger.debug(
                    "[OneBot] %s 取头像失败 user_id=%s: %s",
                    action_name,
                    user_id,
                    exc,
                )
                continue

            url = self._extract_avatar_url(result)
            if not url:
                continue
            if self._is_qq_cdn_avatar_url(url):
                logger.debug(
                    "[OneBot] %s 返回 QQ CDN，继续尝试其他来源 user_id=%s",
                    action_name,
                    user_id,
                )
                continue
            return url
        return None

    async def get_user_avatar_url(
        self,
        user_id: str,
        size: int = 100,
    ) -> str | None:
        """
        获取用户头像 URL。

        优先级：
        1. 本地缓存
        2. 协议端真实头像（WeChatBridge 的 wx.qlogo / avatar_url）
        3. 回退 QQ 官方 CDN（仅真正的 QQ 号有效）
        """
        uid = str(user_id).strip()
        if not uid:
            return None

        cached = self._avatar_url_cache.get(uid)
        if cached:
            return cached

        protocol_url = await self._fetch_avatar_url_from_protocol(uid)
        if protocol_url:
            self._avatar_url_cache[uid] = protocol_url
            logger.debug("[OneBot] 使用协议端真实头像 user_id=%s", uid)
            return protocol_url

        actual_size = self._get_nearest_size(size)
        if actual_size >= 640:
            return self.USER_AVATAR_HD_TEMPLATE.format(user_id=uid, size=640)
        return self.USER_AVATAR_TEMPLATE.format(user_id=uid, size=actual_size)
    # --- {MARKER} end ---
'''


def apply() -> int:
    if not TARGET.exists():
        print(f"ERROR: missing {TARGET}")
        return 2

    text = TARGET.read_text(encoding="utf-8")
    original = text

    if "import asyncio" not in text:
        text = text.replace("import base64\n", "import asyncio\nimport base64\n", 1)

    if "_avatar_url_cache" not in text:
        anchor = "        self._group_role_cache: dict[str, tuple[str, float]] = {}\n"
        if anchor in text:
            text = text.replace(anchor, anchor + CACHE_LINE, 1)
        else:
            anchor = "        self._muted_groups_cache = {}\n"
            if anchor not in text:
                print("ERROR: cannot find __init__ cache anchor")
                return 3
            text = text.replace(anchor, anchor + CACHE_LINE, 1)

    # If patch already present with marker, keep only ensure imports/cache
    if MARKER in text and "async def _fetch_avatar_url_from_protocol" in text:
        if text == original:
            print("ALREADY_APPLIED")
            return 0
        TARGET.write_text(text, encoding="utf-8")
        print("APPLIED_MINIMAL")
        return 0

    # Remove any previous patch helpers/methods by names
    for name in (
        "_is_qq_cdn_avatar_url",
        "_extract_avatar_url",
        "_fetch_avatar_url_from_protocol",
        "get_user_avatar_url",
    ):
        pat = re.compile(rf"(?m)^    (?:async\s+)?def\s+{name}\s*\(")
        while True:
            m = pat.search(text)
            if not m:
                break
            next_pat = re.compile(r"(?m)^    (?:async\s+)?def\s+|^class\s+|^    # --- ")
            n = next_pat.search(text, m.end())
            end = n.start() if n else len(text)
            # also remove trailing blank lines
            while end < len(text) and text[end] == "\n":
                end += 1
            text = text[: m.start()] + text[end:]

    # Remove old marker regions if any
    text = re.sub(
        rf"(?s)\n?    # --- {re.escape(MARKER)} start ---.*?# --- {re.escape(MARKER)} end ---\n?",
        "\n",
        text,
    )

    insert_before = None
    for marker in (
        "    async def get_user_avatar_data(",
        "    async def get_group_avatar_url(",
        "    async def batch_get_avatar_urls(",
    ):
        idx = text.find(marker)
        if idx >= 0:
            insert_before = idx
            break
    if insert_before is None:
        idx = text.find("    # ==================== IAvatarRepository")
        if idx < 0:
            print("ERROR: cannot find avatar section")
            return 5
        insert_before = text.find("\n", idx) + 1

    text = text[:insert_before] + HELPERS_AND_METHOD.rstrip() + "\n\n" + text[insert_before:]

    old_doc = "支持 NapCat, go-cqhttp, Lagrange 等遵循 OneBot v11 协议的 QQ 机器人框架。"
    new_doc = "支持 NapCat, go-cqhttp, Lagrange 等遵循 OneBot v11 协议的 QQ 机器人框架；兼容 WeChatBridge（优先协议端 avatar_url）。"
    if old_doc in text:
        text = text.replace(old_doc, new_doc, 1)

    if text == original:
        print("ALREADY_APPLIED")
        return 0

    TARGET.write_text(text, encoding="utf-8")
    print("APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(apply())
