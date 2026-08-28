# WeChatBridge 维护说明（本 fork）

本仓库是 [SXP-Simon/astrbot_plugin_qq_group_daily_analysis](https://github.com/SXP-Simon/astrbot_plugin_qq_group_daily_analysis) 的 fork：

- **本 fork（安装/更新请用这个）**：https://github.com/muqing-kg/astrbot_plugin_qq_group_daily_analysis
- **上游源**：https://github.com/SXP-Simon/astrbot_plugin_qq_group_daily_analysis

专供 **WeChatBridge**，并附带两套自定义模板：`soft_glass`、`jx3_qban`。

## 分支

| 分支 | 作用 |
|------|------|
| `main` | 上游镜像 + 维护脚本/资源 + 品牌地址重写 |
| `wechat-avatar` | **AstrBot 请用这个分支** = 上游 + 微信头像补丁 + soft_glass + jx3_qban + 品牌地址 |

## 可选模板

AstrBot 插件配置「报告模板」，或命令：

```text
/设置模板 soft_glass
/设置模板 jx3_qban
```

两者都已写入 `_conf_schema.json` options，也会出现在 `/查看模板` 列表（按模板目录自动扫描）。

## 自动同步（无冲突策略）

GitHub Actions：`.github/workflows/auto-sync-upstream.yml`

- 每 6 小时跑一次，也可手动 `Run workflow`
- **不 merge、不手解冲突**（自动拉上游 + 自动重放功能）：
  1. 快照本 fork 维护文件与自定义资源
  2. `main` / `wechat-avatar` 都 `reset --hard upstream/main`
  3. 拷回维护文件/资源
  4. 依次重放补丁：
     - `scripts/apply_wechat_avatar_patch.py`（仅 wechat-avatar）
     - `scripts/apply_soft_glass_template.py`
     - `scripts/apply_jx3_qban_template.py`（透明贴图 + 模板 CSS；CDN 默认走分支，提交后再钉到本 commit）
     - `scripts/apply_t2i_resilience.py`（T2I 兜底策略 + 更稳默认分辨率/超时）
     - `scripts/apply_fork_branding.py`（插件仓库地址改到本 fork；**不改 version**）
  5. `force-with-lease` 推送到 origin；并尽量 purge jsDelivr 分支缓存

因此日常**不要**在 `wechat-avatar` 上堆一次性手工改运行时文件。  
要改补丁 / 模板 / 贴图，只改维护源（改完推到 `wechat-avatar`，或手动跑一次 Action）：

```text
scripts/apply_wechat_avatar_patch.py
scripts/apply_soft_glass_template.py
scripts/apply_jx3_qban_template.py
scripts/apply_t2i_resilience.py
scripts/apply_fork_branding.py
scripts/refill_jx3_emojis.py            # 重做 jx3 表情贴图（保留透明）
assets/custom/templates/soft_glass/     # soft_glass 权威源
assets/custom/soft_glass_character.jpg
assets/custom/jx3_qban/                 # jx3_qban 角色/图标/顶栏图（权威源）
assets/custom/templates/jx3_qban/       # jx3_qban 模板快照（可选，脚本会重建）
.github/workflows/auto-sync-upstream.yml
WECHATBRIDGE.md
```

**保证「拉上游后功能还在」的机制**：上游代码可以整棵换掉，但维护源会快照回来，再由 apply 脚本重放。  
只要功能写进维护源 / apply 脚本，就不会因上游更新而丢。

## soft_glass

- 官方 `scrapbook` 保持原样
- 自定义浅蓝玻璃风独立为：`soft_glass`
- 权威源：`assets/custom/templates/soft_glass/`
- 角色图：`assets/custom/soft_glass_character.jpg`

## jx3_qban

- 基于 ATRI 布局，不覆盖官方 `ATRI`
- 独立模板名：`jx3_qban`
- 角色/图标/顶栏：`assets/custom/jx3_qban/`
- 重建脚本：`scripts/apply_jx3_qban_template.py`
- 文案为唐小珂主题；柱状图等未点名部分保持 ATRI 原结构

## AstrBot 安装

```bash
git clone -b wechat-avatar https://github.com/muqing-kg/astrbot_plugin_qq_group_daily_analysis.git astrbot_plugin_qq_group_daily_analysis
```

更新：

```bash
cd astrbot_plugin_qq_group_daily_analysis
git fetch origin
git checkout wechat-avatar
git reset --hard origin/wechat-avatar
# 重启 AstrBot
# /设置模板 soft_glass  或  /设置模板 jx3_qban
```

## 补丁做什么

### 1) 微信头像
`onebot_adapter.get_user_avatar_url`：

1. 先调 `get_stranger_info` / `get_user_info` 读 `avatar` / `avatar_url`
2. 若是 `wx.qlogo` 等真实地址则使用
3. 否则才回退 QQ CDN

### 2) 品牌地址
`apply_fork_branding.py` 会把 `metadata.yaml` / README / 模板页脚中的插件仓库地址改到：

`https://github.com/muqing-kg/astrbot_plugin_qq_group_daily_analysis`

**版本号策略**：`metadata.yaml` 的 `version` / `astrbot_version` 始终直接使用上游值。  
第三方资源（如 `SXP-Simon/profile_assets` CDN）保持原样。
