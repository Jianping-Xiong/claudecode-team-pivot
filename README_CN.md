# claudecode-team-pivot

> **个人实验工具。** 不是 team-pivot-web 的官方客户端，为我自己的 AI-native CLI 工作流做的。一个人维护，无 SLA，欢迎 issue / PR。

Claude Code **APP**（[Agent Pipeline Protocol v0.4](https://github.com/hashSTACS-Global/agent-pipeline-protocol)），用自然语言和 [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) 讨论平台交互——浏览讨论、AI 起草回复（带强制确认闸门）、@ 同事、搜讨论历史、周度汇总。

两条执行通路：
- **`runner.py` 跑 pipeline**：多步流程、框架强制 preflight、含 LLM 步（read / reply / draft / digest），与 Claude Code 通过 `{status:paused, llm_request:{...}}` / `resume` 协议交接
- **`bin/pivot.py` 原子命令**：单次 API 调用（threads / show / contacts / mention / status / favorite / read / sync / search / history / me），零依赖，不要 PyYAML

## 前置依赖

- **Claude Code** 已安装（`~/.claude/skills/` 存在或可创建）
- **Python 3.8+** — macOS Ventura+ 不再预装 Python，需从 [python.org](https://www.python.org/downloads/) 或 Homebrew (`brew install python`) 装；Windows 用 python.org 的安装器自动加 PATH
- **PyYAML** — `runner.py` pipeline 必需。`python3 -m pip install pyyaml`。（`bin/pivot.py` 原子命令不需要）
  - macOS Ventura+ 用 python.org 安装器可能撞 PEP 668 `externally-managed-environment` 错。三种处理（按推荐序）：
    1. `brew install python` 然后 `python3 -m pip install pyyaml`（最干净）
    2. `python3 -m pip install --user pyyaml`（装到用户级 site-packages）
    3. `python3 -m pip install --break-system-packages pyyaml`（最后手段，用便利换掉安全边界）
- **git** — macOS 预装（首次使用时弹 Xcode Command Line Tools 安装）或 `brew install git`；Windows 从 [git-scm.com](https://git-scm.com/) 装
- **ripgrep (`rg`)**（可选） — 全文搜索快 5-10×。macOS `brew install ripgrep` / Windows `winget install BurntSushi.ripgrep.MSVC` / 或 [release page](https://github.com/BurntSushi/ripgrep/releases)。没装时自动 fallback 到 `git grep`

相关官方项目（由 Pivot 团队维护，与本 skill 独立）：[team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web)（服务端 + Web UI）、[vscode-team-pivot](https://github.com/hashSTACS-Global/vscode-team-pivot)、[intellij-team-pivot](https://github.com/hashSTACS-Global/intellij-team-pivot)。

English: [README.md](README.md)

## Installation

### agent 一键装

把下面这段发给 Claude Code：

```
按 https://github.com/Jianping-Xiong/claudecode-team-pivot 的 README Installation 章节帮我装。
```

Claude 会按当前 OS 挑下面对应的命令执行，并引导你配 PAT。

### 手动安装 · macOS / Linux

```bash
# 1. clone 到本地工作区
#    SSH（推荐：已配 GitHub SSH key 的机器）：
git clone git@github.com:Jianping-Xiong/claudecode-team-pivot.git \
  ~/repository/claudecode-team-pivot
#    HTTPS（备用：这台机器没配 SSH key）：
# git clone https://github.com/Jianping-Xiong/claudecode-team-pivot.git \
#   ~/repository/claudecode-team-pivot

# 2. 软链到 Claude Code skill 目录
mkdir -p ~/.claude/skills
ln -s ~/repository/claudecode-team-pivot ~/.claude/skills/claudecode-team-pivot

# 3. 建配置文件（下面的 runner.py setup 会填内容，也可以直接手改）
mkdir -p ~/.pivot
cp ~/.claude/skills/claudecode-team-pivot/config.example.json ~/.pivot/config.json
```

### 手动安装 · Windows

重要：Git Bash 的 `ln -s` 在默认环境（没开 Dev Mode、也没设 `MSYS=winsymlinks:nativestrict`）下会**静默退化成完整复制**。复制意味着改源码不会同步到 skill 目录。**推荐用 directory junction**——不需要管理员、不需要 Dev Mode。

推荐 PowerShell：对含中文字符的用户目录（比如 `C:\Users\熊剑平`）处理更干净。Git Bash 也行但路径语法要当心。

**PowerShell**（推荐）：

```powershell
# 1. clone 到本地（盘符按实际调整）
git clone git@github.com:Jianping-Xiong/claudecode-team-pivot.git `
  D:\repository\claudecode-team-pivot

# 2. 建 junction
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\skills" | Out-Null
New-Item -ItemType Junction `
  -Path "$env:USERPROFILE\.claude\skills\claudecode-team-pivot" `
  -Target "D:\repository\claudecode-team-pivot"

# 3. 建配置文件
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.pivot" | Out-Null
Copy-Item D:\repository\claudecode-team-pivot\config.example.json `
  "$env:USERPROFILE\.pivot\config.json"
```

> PowerShell 注意：**不要**在 Windows PowerShell 5.1 下用 `Set-Content -Encoding UTF8` 重写 config——会加 UTF-8 BOM。上面的 `Copy-Item` 保留源文件编码，安全。要从头生成就用：`[System.IO.File]::WriteAllText("$env:USERPROFILE\.pivot\config.json", $content, (New-Object System.Text.UTF8Encoding $false))`。本 skill 用 `utf-8-sig` 读配置已经容忍 BOM，但其他工具未必。

**Git Bash**（替代方案——注意 junction 那步仍推荐调用 PowerShell，`ln -s` 不安全）：

```bash
# 1. clone
git clone git@github.com:Jianping-Xiong/claudecode-team-pivot.git \
  /d/repository/claudecode-team-pivot

# 2. 建 junction——委托给 PowerShell，Unicode 路径安全
mkdir -p ~/.claude/skills
powershell.exe -NoProfile -Command \
  'New-Item -ItemType Junction `
    -Path "$env:USERPROFILE\.claude\skills\claudecode-team-pivot" `
    -Target "D:\repository\claudecode-team-pivot"'

# 3. 建配置文件（Git Bash 路径是 Unix 风格 /d/... /c/...）
mkdir -p ~/.pivot
cp /d/repository/claudecode-team-pivot/config.example.json ~/.pivot/config.json
```

验证建的是真 junction 不是复制：

```powershell
(Get-Item "$env:USERPROFILE\.claude\skills\claudecode-team-pivot").LinkType
# 期望输出：Junction
```

### 配 PAT（全平台通用）

最快走**交互式 setup**：

```bash
# macOS / Linux
python3 ~/.claude/skills/claudecode-team-pivot/runner.py setup

# Windows（PowerShell）
python "$env:USERPROFILE\.claude\skills\claudecode-team-pivot\runner.py" setup
```

它会问你：
1. **你们团队的 Pivot 服务器 URL**（形如 `https://pivot.<your-team>.com`——登 Pivot Web 时用的那个域名）
2. **PAT token**——在 `<base-url>/settings/api-tokens` 生成。命名按设备 + 客户端（`mac-cc` / `windows-cc`，不要和 `*-vs-code` 混用）。明文**只显示一次**，立即复制

setup 会把 `~/.pivot/config.json` 写成 UTF-8 无 BOM，并立刻跑 constructor 端到端校验，成功输出 `status: completed` + 下一步建议命令。

非交互（脚本化 / AI agent 驱动）：

```bash
python runner.py setup --base-url https://pivot.<your-team>.com --token pvt_xxx
```

**手动替代**：`cp config.example.json ~/.pivot/config.json`，编辑 `base_url` + `token`，然后 `python runner.py check-init` 验证。

**验证命令**：

```bash
python runner.py check-init   # 或 python bin/pivot.py me
```

`initialized: true` 或返你 profile 的 JSON 就通了。`[401:invalid_token]` 说明 token 错/过期/签发自别的域名（token 和 base_url 必须来自同一个部署）。

### 升级

装法是软链 / junction，升级只要**在本地 repo 里 `git pull`**——`~/.claude/skills/claudecode-team-pivot` 因为是链接，自动看到新文件，不用重装。

```bash
cd ~/repository/claudecode-team-pivot          # 或 Windows 下 D:\repository\...
git pull
python -m pip install --upgrade pyyaml          # 只有新增次要依赖时才需要
python runner.py check-init                     # 安康检查
```

升级**纯叠加**——加文件、加可选运行时目录（`~/.pivot/sessions/` / `~/.pivot/drafts/`），不删不改。config 结构稳定，PAT、mirror clone、用户数据都不动。

回滚：在同一个 clone 里 `git checkout <旧 tag>`。

### 给 AI agent 装这个 skill 看

如果你是 Claude Code 或别的 agent 在帮用户装，读这段：

**这三件事必须问用户** — 不要默认：
1. **安装路径** — 默认建议 `~/repository/claudecode-team-pivot`（macOS/Linux）或 `D:\repository\claudecode-team-pivot`（Windows），但用户可能偏好 `~/Codes/` 之类
2. **Pivot 服务器 `base_url`** — 团队内部唯一，用户自己知道；**问他们**"你平时登 Pivot Web 用哪个 URL？"，别默认任何域名
3. **PAT token** — 用户自己去 `<base-url>/settings/api-tokens` 生成（明文只给一次）。让用户粘过来；不要尝试帮他们自动化

**有 setup 交互命令专门干这事**：

```bash
python runner.py setup
```

它按顺序问 base_url + token，写文件，跑校验——一条命令搞定。**agent 优先用它，别手动拼文件**。

**常见失败模式要认得**：
- `YOUR_DOMAIN placeholder` → base_url 还在模板值；问用户真实 URL
- `[401:invalid_token]` → token 错/过期，或 token 是别的域名签发的
- `[0:network_error]` → base_url 不通（没开 VPN？拼错？）
- `requires PyYAML` → 跑 `python -m pip install pyyaml`

### 卸载

```bash
# macOS / Linux / Windows (Git Bash)
rm ~/.claude/skills/claudecode-team-pivot

# Windows（cmd，如果装的时候用的是 mklink /J）
rmdir "%USERPROFILE%\.claude\skills\claudecode-team-pivot"
```

`~/repository/` 下的 clone 不动；想删自己删。

## 使用

在 Claude Code 里直接用自然语言：

- "pivot 上有啥新讨论"
- "帮我看下 proposals/database-migration 那个讨论"
- "给这个 thread 回一句：同意方案 A，先在测试环境跑一周"
- "pivot 上谁提过 ClickHouse"
- "这周讨论的重点是什么"

Skill 会自动编排 REST API 调用和（可选）本地 git mirror 操作。任何写入操作（回复、@、改状态）**都会先展示草稿给你 review 确认**才发布。

## 命令

### Pipeline（`runner.py`）

多步流程；有 LLM 推理 / 确认闸门时用。

| 命令 | 作用 | 含 LLM 步 |
|---|---|---|
| `runner.py setup [--base-url U --token T]` | 交互式首次配置 | 无 |
| `runner.py check-init` | 预检（config + token） | 无 |
| `runner.py list` | 列可用 pipeline | 无 |
| `runner.py read --thread <cat>/<slug>` | 抓 + 总结 thread + 建议下一步 | 有（summarize） |
| `runner.py reply --thread <cat>/<slug> --draft-file F [...]` | 发回复，强制确认闸门 | 有（confirm） |
| `runner.py draft --thread <cat>/<slug> --content-file F` | 草稿持久化到 `~/.pivot/drafts/`，校验 frontmatter | 无 |
| `runner.py digest --since 7d` | sync + 按 thread 分组的 commit 汇总 | 有（group） |
| `runner.py resume <session> --llm-output '<json>'` | LLM 工作完成后恢复暂停 pipeline | — |

暂停时 runner 返 `{"status": "paused", "llm_request": {...}}`，调用方 agent 做 LLM 工作后 `resume`。

### 原子命令（`bin/pivot.py`）

每个都是单次 API / subprocess 调用；不需要 PyYAML。

| 命令 | 作用 |
|---|---|
| `pivot.py me` | 验证 token + 打印服务端/工作区信息 |
| `pivot.py threads [--unread-first] [--category X] [--limit N]` | 列 thread |
| `pivot.py show <cat>/<slug>` | thread 详情（posts + mentions） |
| `pivot.py reply <cat>/<slug> --file F [--mention ids --mention-comment C]` | 发回复（**无确认闸门**，新代码建议走 `runner.py reply`） |
| `pivot.py new <cat> --title T --file F` | 新 thread |
| `pivot.py mention <cat>/<slug> --target-filename FN --mention ids --mention-comment C` | 独立 @ |
| `pivot.py status <cat>/<slug> --to STATE [--reason R]` | 改状态 |
| `pivot.py favorite <cat>/<slug> [--unfavorite]` | 收藏/取消 |
| `pivot.py read <cat>/<slug>` | 标记已读 |
| `pivot.py contacts [--search Q]` | 按名字查 open_id |
| `pivot.py sync [--check]` | clone / pull 本地镜像 |
| `pivot.py search <pattern>` | 镜像里全文搜 |
| `pivot.py history [--since 7d]` | 镜像 git log 摘要 |

完整参数 `pivot.py --help` 和 `runner.py --help`。

## 架构

```
~/.pivot/config.json             # PAT + base_url + mirror_dir
        │
        ▼
bin/pivot.py                     # 瘦 CLI 派发（argparse）
   ├── api.py                    # REST 封装（urllib，零依赖）
   ├── mirror.py                 # git clone/pull（可选）
   └── search.py                 # ripgrep / git grep
        │
        ▼
team-pivot-web REST API          ← 所有写入走这
        + git mirror（只读）     ← 读可选走这里加速
```

- **写入永远走 REST**——服务端做原子 commit
- **读默认走 REST** 保证新鲜；git mirror 是全文搜和大上下文场景的加速层
- Mirror 默认路径 `~/pivot-mirror/`——**故意和 vscode-team-pivot 一致**，两个客户端共用一份 clone

## 配置

优先级：环境变量 > `~/.pivot/config.json` > 内置默认值

| 字段 | 环境变量 | 默认值 |
|---|---|---|
| `base_url` | `PIVOT_BASE_URL` | `https://pivot.enclaws.ai` |
| `token` | `PIVOT_TOKEN` | *（必填）* |
| `mirror_dir` | `PIVOT_MIRROR_DIR` | `~/pivot-mirror` |

> 内置 `base_url` 默认值只是占位。团队内部通常指向生产域名（比如 `https://pivot.enclaws.com`），装完之后到 `~/.pivot/config.json` 里改 `base_url`。装完 `pivot.py me` 报 `[0:network_error]` 基本就是这个原因。

## 相关项目

- [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) — 服务端 + Web UI，REST 契约源头
- [vscode-team-pivot](https://github.com/hashSTACS-Global/vscode-team-pivot) — VS Code 扩展
- [intellij-team-pivot](https://github.com/hashSTACS-Global/intellij-team-pivot) — IntelliJ 插件

## License

MIT
