from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from kwok.config import KwokConfig

SERVER_MODULE = "kwok.server"

_START_TIMEOUT_SECONDS = 5.0
_STOP_GRACE_SECONDS = 5.0
_POLL_INTERVAL_SECONDS = 0.1
_PROBE_TIMEOUT_SECONDS = 0.5
_PS_TIMEOUT_SECONDS = 2.0


def _kwok_dir() -> Path:
    return Path("~/.kwok").expanduser()


def _pid_file(port: int) -> Path:
    return _kwok_dir() / f"kwok-server-{port}.pid"


def _stderr_log_path() -> Path:
    return _kwok_dir() / "logs" / "daemon.log"


def _read_pid(port: int) -> int | None:
    try:
        raw = _pid_file(port).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw.isdigit():
        return None
    return int(raw)


def _write_pid(port: int, pid: int) -> None:
    path = _pid_file(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def _remove_pid_file(port: int) -> None:
    _pid_file(port).unlink(missing_ok=True)


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _command_line(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=_PS_TIMEOUT_SECONDS,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _is_kwok_server(pid: int) -> bool:
    cmdline = _command_line(pid)
    return "kwok.server" in cmdline or "kwok-server" in cmdline


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _wait_exit(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_alive(pid):
            return True
        time.sleep(_POLL_INTERVAL_SECONDS)
    return False


def start_server(config: KwokConfig) -> int:
    pid = _read_pid(config.port)
    if pid is not None and _is_alive(pid) and _is_kwok_server(pid):
        print(f"kwok-server 已在运行（pid={pid}，监听 {config.host}:{config.port}），无需启动")
        return 0
    if _is_port_open(config.host, config.port):
        print(
            f"端口 {config.port} 已被占用且无有效 PID 文件（疑似手动启动的实例），拒绝启动",
            file=sys.stderr,
        )
        return 1
    log_path = _stderr_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as stderr_file:
        proc = subprocess.Popen(
            [sys.executable, "-m", SERVER_MODULE],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
            start_new_session=True,
        )
    _write_pid(config.port, proc.pid)
    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            _remove_pid_file(config.port)
            print(
                f"kwok-server 启动失败（退出码 {proc.returncode}），详情见 {log_path}",
                file=sys.stderr,
            )
            return 1
        if _is_port_open(config.host, config.port):
            print(f"kwok-server 已启动（pid={proc.pid}，监听 {config.host}:{config.port}）")
            return 0
        time.sleep(_POLL_INTERVAL_SECONDS)
    _remove_pid_file(config.port)
    print(
        f"kwok-server 启动超时（{_START_TIMEOUT_SECONDS:.0f}s 内端口未就绪）",
        file=sys.stderr,
    )
    return 1


def stop_server(config: KwokConfig) -> int:
    pid = _read_pid(config.port)
    if pid is None:
        if _is_port_open(config.host, config.port):
            print(
                f"端口 {config.port} 有服务在监听但无 PID 文件（疑似手动启动），无法安全停止",
                file=sys.stderr,
            )
            return 1
        print(f"kwok-server 未在运行（port={config.port}）")
        return 0
    if not _is_alive(pid) or not _is_kwok_server(pid):
        _remove_pid_file(config.port)
        print(f"kwok-server 未在运行（已清理陈旧 PID 文件，pid={pid}）")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _remove_pid_file(config.port)
        print(f"kwok-server 已停止（pid={pid}）")
        return 0
    if _wait_exit(pid, _STOP_GRACE_SECONDS):
        _remove_pid_file(config.port)
        print(f"kwok-server 已停止（pid={pid}）")
        return 0
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    _remove_pid_file(config.port)
    print(f"kwok-server 优雅停机超时，已强制终止（pid={pid}）", file=sys.stderr)
    return 0


def status_server(config: KwokConfig) -> int:
    pid = _read_pid(config.port)
    managed = pid is not None and _is_alive(pid) and _is_kwok_server(pid)
    reachable = _is_port_open(config.host, config.port)
    if managed and reachable:
        print(f"kwok-server 运行中：pid={pid}，监听 {config.host}:{config.port}")
        return 0
    if reachable:
        print(f"kwok-server 运行中（无 PID 文件，疑似手动启动）：监听 {config.host}:{config.port}")
        return 0
    if managed:
        print(f"kwok-server 进程存活（pid={pid}），但 {config.host}:{config.port} 未监听")
        return 1
    if pid is not None:
        print(f"kwok-server 未运行（PID 文件陈旧：pid={pid}）")
        return 1
    print(f"kwok-server 未运行（{config.host}:{config.port} 无监听）")
    return 1


def restart_server(config: KwokConfig) -> int:
    stop_code = stop_server(config)
    if stop_code != 0:
        return stop_code
    return start_server(config)


_ACTIONS: dict[str, Callable[[KwokConfig], int]] = {
    "start": start_server,
    "stop": stop_server,
    "status": status_server,
    "restart": restart_server,
}


def run_server_action(action: str, config: KwokConfig) -> int:
    handler = _ACTIONS.get(action)
    if handler is None:
        print(f"未知 server 子命令：{action}", file=sys.stderr)
        return 2
    return handler(config)
