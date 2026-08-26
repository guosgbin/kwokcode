# KwokCode

> 本地终端 AI 编程助手｜自研 Skill 系统｜JSON-RPC 守护进程架构

类似 Claude Code，完全本地实现，用于在终端完成代码阅读、修改、调试、项目重构。

## 特性

- 终端交互式会话，流式大模型输出 + 思考过程（reasoning）实时展示
- Skill 技能系统：可扩展自定义技能，隔离工具白名单
- Sub-agent 协作：`spawn_agent` 派生隔离子代理，Planner / Reviewer / Implementer 内置角色，支持后台任务
- MCP（Model Context Protocol）接入：外部 MCP 服务端工具注入为普通工具
- TCP JSON-RPC 2.0 服务端/客户端分离架构（daemon 后台常驻）
- 异步事件总线：会话事件、LLM 流、工具调用全链路事件推送
- 会话持久化：会话记录、项目级记忆、会话级记忆
- 命令行子命令：`prompt` / `interactive` / `ping` / `version`
- NDJSON 结构化日志，区分控制台人类可读格式 / JSON 机器格式

## 快速开始

```bash
# 安装依赖
pip install -e .

# 启动守护进程
kwok server start

# 进入交互式会话
kwok interactive

# 或直接提问
kwok prompt "解释一下 src/kwok/server/session/manager.py 的架构"
```

## 命令行使用

### interactive 交互模式

```bash
kwok interactive
```

进入 TUI 交互式会话，支持：

- `Enter` 发送消息
- `Ctrl+J` 换行
- `↑/↓` 浏览历史
- `Ctrl+Y` 复制选中文本
- `/compact` 压缩上下文
- `/skill_name <args>` 触发 Skill
- 思考过程实时展示（reasoning 模型，如 DeepSeek-R1）

### prompt 单次提问

```bash
kwok prompt "你的问题"
```

直接发起 chat，流式输出大模型回复后退出。

### ping / version 运维命令

```bash
kwok ping        # 测试服务端连通性
kwok version     # 打印服务端版本号
```

### server 守护进程管理

```bash
kwok server start    # 后台启动 kwok-server
kwok server stop     # 停止运行中的守护进程
kwok server status   # 查看运行状态
kwok server restart  # 重启守护进程
```

守护进程使用 PID 文件（`~/.kwok/kwok-server-{port}.pid`）管理生命周期，端口级隔离。

## Skill 技能系统

Skill 是面向用户的"命令式"能力封装层：用户输入 `/skill_name <args>` 触发 → 解析 Markdown 模板 → 同时产出系统提示覆盖和工具白名单两个维度，下传给一次 run。

### Skill 文件格式规范

每个 Skill 是一个 `<name>/SKILL.md` 目录，文件结构为 YAML frontmatter + Markdown 正文：

```markdown
---
name: review
description: 审查指定文件或目录的代码质量
allowed_tools:
  - read_file
  - grep
---
请对以下代码区域做一次代码审查：$ARGUMENTS

重点检查：
- 正确性：是否存在明显 bug、边界处理缺失
- 可读性：命名、结构、职责是否清晰
- 安全性：是否引入安全隐患
```

- `name`：Skill 名称（必填，缺失则视为非法 Skill）
- `description`：简要描述（弹层候选展示用）
- `allowed_tools`：工具白名单（可选，空则不设限）
- `$ARGUMENTS`：占位符，运行时替换为用户实参
- 正文：作为 system prompt 覆盖默认提示词

### 加载优先级：本地项目 → 用户全局 → 内置

```
1. .kwok/skills/          # 项目本地（最高优先）
2. ~/.kwok/skills/        # 用户全局
3. 内置 prebuilt/         # 兜底
```

同名 Skill 本地版本覆盖全局与内置。

### 编写自定义 Skill

在项目根目录创建 `.kwok/skills/<name>/SKILL.md`：

```bash
mkdir -p .kwok/skills/my-skill
cat > .kwok/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: 我的自定义技能
allowed_tools:
  - read_file
  - edit
---
请完成以下任务：$ARGUMENTS
EOF
```

然后在 TUI 中输入 `/my-skill 具体任务描述` 即可触发。

## Sub-agent 协作系统

主 agent 可通过 `spawn_agent` 工具派生隔离的子 agent 执行子任务，实现多角色协作与并行执行。

### 内置角色

| 角色 | 职责 | 工具白名单 |
|------|------|-----------|
| **planner** | 只读分析、拆解有序步骤 | read / glob / grep / 记忆读取 |
| **implementer** | 严格按计划执行，含写工具 | bash / write / edit / read / glob / grep / 记忆读写 |
| **reviewer** | 只读核查实际产出，可运行 bash 验证 | bash / read / glob / grep / 记忆读取 |

角色即文件：每个角色是一个 Markdown 文件（frontmatter 定义元数据，正文为该角色的系统提示词），通过三级加载链解析，与 Skill 系统同构。

### spawn_agent / agent_result / cancel_task

| 工具 | 说明 |
|------|------|
| `spawn_agent` | 派生子 agent：前台阻塞等待结果；`run_in_background=true` 立即返回 turn_id |
| `agent_result` | 查询后台任务状态：running / cancelled / exception / result |
| `cancel_task` | 显式取消后台任务；已完成/不存在为安全 no-op |

子 agent 的隔离机制：

- **工具物理隔离**：按角色白名单构建独立 ToolRegistry，未注册工具直接不可见（fail-closed）
- **冷启动**：角色正文替换 base system prompt，不继承父对话历史与记忆
- **事件桥接**：子事件落盘 `<session>/turns/<child_turn_id>/event.jsonl` 并转发父 bus，TUI 可实时观测
- **嵌套限制**：最多一层嵌套，子 agent 内禁止再次 `spawn_agent`
- **断连级联取消**：客户端断连时自动取消其名下所有后台子任务

### 编写自定义角色

角色目录布局 `<dir>/<name>.md`，加载优先级同 Skill（本地 → 全局 → 内置）：

```bash
mkdir -p .kwok/subagent
cat > .kwok/subagent/tester.md << 'EOF'
---
name: tester
description: 运行测试并分析失败原因
tools: bash, read, grep
---
你是一名测试工程师。被调用时，运行给定测试并逐条分析失败原因，输出可落地的修复建议。
EOF
```

`tools` 支持单行逗号分隔或块列表两种写法；可选 `model:` 字段指定子 agent 模型（缺省继承父 agent）。

## MCP 工具接入

通过标准 MCP（Model Context Protocol）协议接入外部工具服务端，MCP 工具注入后与内置工具同权使用（参数校验 → 权限审批 → 执行 → 事件全链路治理）。

### 配置

配置文件双层叠加：`~/.kwok/mcp.json`（用户全局）+ `.kwok/mcp.json`（项目本地）：

```json
{
  "mcpServers": {
    "demo_mcp": {
      "transport": "stdio",
      "command": "/path/to/mcp-server"
    }
  }
}
```

- 支持 `stdio` 与 `Streamable HTTP` 两种传输
- 每个外部服务端暴露的工具以 `{server}__{tool}` 命名注册进工具表，schema 透传

## 会话 & 记忆机制

### 会话 ID 与 turn-id

- **Session ID**：标识一次完整的交互式会话（`sess=20260826-005119-d31b56`）
- **Turn ID**：标识会话中的单轮对话
- **Step ID**：标识 turn 内的单个执行步骤

### 会话级记忆

每次会话的完整交互记录（用户消息、LLM 回复、工具调用）持久化存储，支持上下文回溯。

### 项目级持久记忆

通过 `KWOK.md` 文件实现两层静态记忆：

```
~/.kwok/KWOK.md      # Global：跨项目通用记忆
.kwok/KWOK.md        # Project：当前项目专属记忆
```

在 `send_message()` 时自动加载，注入到 system prompt 的记忆层。

## 架构说明

### 守护进程与客户端分离

```
┌─────────────┐     TCP (127.0.0.1:6456)     ┌──────────────┐
│  kwok-cli   │ ◄──────────────────────────► │  kwok-server │
│  kwok-tui   │     JSON-RPC 2.0 / NDJSON    │  (daemon)    │
└─────────────                              └──────────────┘
```

- **kwok-server**：后台常驻守护进程，持有 LLM 连接、工具注册表、会话状态
- **kwok-cli / kwok-tui**：轻量客户端，通过 TCP 与 server 通信

### JSON-RPC 2.0 IPC 通信

协议方法：

| Method | 说明 |
|--------|------|
| `ping` | 连通性测试 |
| `version` | 获取服务端版本 |
| `prompt` | 发起对话 |
| `session.create` | 创建新会话 |
| `session.prompt` | 发送消息 |
| `session.close` | 关闭会话 |
| `session.compact` | 压缩上下文 |
| `event.subscribe` | 订阅事件流 |
| `event.unsubscribe` | 取消订阅 |
| `permission.respond` | 回复权限审批 |

### 事件总线 EventBus 设计

```
Server Event → EventBusManager → ClientEventPush → TCP → TUI/CLI
```

- 会话事件、LLM 流式输出、工具调用、权限请求均通过事件总线推送
- 客户端通过 `event.subscribe` 订阅感兴趣的事件类型
- 支持按模式过滤（如 `turn.*`、`tool.**`）

### 项目目录结构

```
src/kwok/
├── cli/                  # 命令行客户端
│   ├── arg_parser.py     # 子命令定义
│   ├── cmd/              # 命令实现（prompt/interactive/ping/version）
│   └── main.py           # CLI 入口
├── tui/                  # TUI 终端界面
│   ├── app.py            # 主应用
│   ├── client.py         # TUI 客户端
│   ├── renderer.py       # 事件渲染器
│   └── widgets/          # UI 组件（输入面板、命令弹层、转录区等）
├── server/               # 服务端核心
│   ├── main.py           # Server 入口
│   ├── session/          # 会话管理
│   ├── skill/            # Skill 系统
│   ├── subagent/         # Sub-agent 协作（角色加载/运行/后台任务）
│   ├── mcp/              # MCP 外部工具接入
│   ├── tools/            # 工具注册与实现
│   ├── event/            # 事件总线
│   ├── memory/           # 记忆系统
│   ├── permissions/      # 权限管理
│   └── llm/              # LLM 调用与流式处理
├── protocol/             # 协议定义（RPC 模型、事件类型）
├── net/                  # 网络层（TCP server/client）
── config.py             # 配置管理
```

## 配置文件

配置文件路径：`~/.kwok/config.toml`

也可通过环境变量覆盖：

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `KWOK_HOST` | 服务端地址 | `127.0.0.1` |
| `KWOK_SERVER_PORT` | 服务端端口 | `6456` |
| `KWOK_TIMEOUT` | 客户端超时（秒） | `3.0` |
| `OPENAI_API_KEY` | LLM API Key | - |
| `OPENAI_BASE_URL` | LLM API Base URL | - |
| `OPENAI_MODEL` | LLM 模型名 | `gpt-4o-mini` |
| `KWOK_LLM_TIMEOUT` | LLM 调用超时（秒） | `60.0` |
| `KWOK_LLM_REASONING_EFFORT` | 推理力度（如 low/medium/high） | 未设置（不改默认请求行为） |
| `KWOK_MAX_STEPS` | 单 turn 最大步骤数 | `20` |
| `KWOK_LOG_LEVEL` | 日志级别 | `INFO` |
| `KWOK_LOG_FILE` | 日志文件路径 | `~/.kwok/logs/core.log` |
| `KWOK_LOG_FORMAT` | 日志格式（text/json） | `text` |

## 开发 & 调试

### 本地运行

```bash
# 直接启动 server（非 daemon 模式，便于调试）
python -m kwok.server.main

# 启动 TUI
python -m kwok.tui.main
```

### 日志查看

```bash
# 实时查看日志
tail -f ~/.kwok/logs/core.log

# JSON 格式日志（便于机器解析）
KWOK_LOG_FORMAT=json kwok server start
```

### PID 文件与服务启停

```bash
# 查看 PID
cat ~/.kwok/kwok-server-6456.pid

# 手动停止
kill $(cat ~/.kwok/kwok-server-6456.pid)
```

### 调试 JSON-RPC 报文

```bash
# 直接发送 RPC 请求
echo '{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}' | nc 127.0.0.1 6456
```

## 已知限制

- Skill 系统目前只支持目录布局 `<name>/SKILL.md`，不支持扁平 `name.md`
- Bash 工具黑名单仅拦截根目录/家目录/工作区整删，子目录删除未拦截
- 工具白名单收缩时，未注册的工具名被安全忽略（无报错）
- 子 agent 最多一层嵌套（子 agent 内不可再派生）
- 思考过程（reasoning）仅内存展示：不落盘、不回传模型
