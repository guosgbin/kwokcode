# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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