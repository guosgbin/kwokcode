"""工具权限审批子系统（设计稿 core/permissions/）。

PermissionManager 进程级单例 + 消费方统一入口：
    from kwok.server.permissions import get_permission_manager
"""

from kwok.server.permissions.manager import (
    PermissionManager,
    get_permission_manager,
    init_permissions,
    reset_permissions,
)

__all__ = [
    "PermissionManager",
    "get_permission_manager",
    "init_permissions",
    "reset_permissions",
]
