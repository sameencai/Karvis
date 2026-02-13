# -*- coding: utf-8 -*-
"""
Karvis 统一存储接口
自动检测运行模式：
  - OneDrive 模式（配置了 ONEDRIVE_CLIENT_ID）→ 使用 OneDriveIO
  - Lite 模式（未配置）→ 使用 LocalFileIO（本地文件系统）

所有模块统一 from storage import IO 即可，无需关心后端。
"""
import sys

def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def _detect_storage_backend():
    """检测并返回合适的存储后端类"""
    from config import ONEDRIVE_CLIENT_ID

    if ONEDRIVE_CLIENT_ID and ONEDRIVE_CLIENT_ID not in ("", "your-onedrive-client-id"):
        _log("[Storage] 检测到 OneDrive 配置 → 使用 OneDrive 模式")
        from onedrive_io import OneDriveIO
        return OneDriveIO
    else:
        _log("[Storage] 未配置 OneDrive → 使用 Lite 本地模式")
        from local_io import LocalFileIO
        return LocalFileIO


# 全局存储实例（模块加载时确定，运行期间不变）
IO = _detect_storage_backend()

# 导出 STORAGE_MODE 供其他模块判断
STORAGE_MODE = "onedrive" if IO.__name__ == "OneDriveIO" else "local"
