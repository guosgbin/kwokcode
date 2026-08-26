# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-08-26

### Added

- 新增 Skill 技能系统：可扩展自定义技能，隔离工具白名单，支持 `/skill_name <args>` 触发
- 新增 Sub-agent 协作系统：`spawn_agent` 派生隔离子代理，支持 Planner / Reviewer / Implementer 内置角色与后台任务
- 新增 MCP 工具接入：支持外部 MCP 服务端工具注入为普通工具（stdio / Streamable HTTP 传输）
- 新增 `~/.kwok/setting.json` 层级配置（setting.json → `.env` → 环境变量）
- TUI 支持模型思考过程（reasoning）实时展示

### Changed

- 命令入口统一为 `kwok`
- MCP 服务端列表从 setting.json 拆分为独立的 `~/.kwok/mcp.json` 双层叠加

## [0.4.0] - 2026-08-25

### Added

- 支持 TUI 交互式命令行
- 新增项目记忆工具：`read_project_memory` / `read_project_memory_idx`
- 新增 Bash 工具，支持 shell 命令执行与超时管理
- 新增 Write 工具，per-session 文件读取跟踪，未读文件禁止覆写
- 新增 Edit 工具，精确字符串替换，支持 TUI 行号级 diff 渲染
- 新增 Grep 工具（基于 ripgrep）与 Glob 工具（文件名模式查找）
- 新增工具权限审批子系统，高危操作需用户批准，含审批缓存
- 新增系统高危命令黑名单（权限层强制拒绝，附友好提示）
- 项目记忆索引（MEMORY.md）自动注入 LLM system 消息

### Changed

- 工具执行链重构为中间件拦截，事件发布由 ToolRunner 解耦到中间件
- 中间件链路重构，统一工具调用前后处理顺序

## [0.3.0] - 2026-08-24

### Added

- 新增会话管理与持久化
- 新增交互式会话模式：`kwok-cli interactive`
- 工具体系重构

### Changed

- 事件系统重构为集中式管理：进程级单例注册中心
- 配置管理重构为进程级配置快照

## [0.2.0] - 2026-08-23

### Added

- Middleware 中间件系统，支持 around/before/after 钩子，model 和 tool 独立排序
- ToolEventMiddleware，将工具事件发布从 ToolRunner 解耦为中间件

## [0.1.0] - 2026-08-22

### Added

- 双进程 `kwok-server` + `kwok-cli` 骨架，JSON-RPC 2.0 + NDJSON 通信
- 事件总线与 IPC 推送，支持客户端订阅事件流
- LLM 流式对话，服务端生成 `turn_id`，逐增量推送事件
- 工具调用框架，支持多轮自动循环
- 守护进程管理（`kwok-cli server start|stop|status|restart`）