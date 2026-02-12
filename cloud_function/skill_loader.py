# -*- coding: utf-8 -*-
"""
Karvis Skill 热加载器（O-010）
自动扫描 skills/ 目录下所有模块，收集 SKILL_REGISTRY 注册表。
新增 skill 只需在模块末尾声明 SKILL_REGISTRY = {"skill.name": handler_fn}，
无需修改 brain.py。
"""
import os
import sys
import importlib

def _log(msg):
    print(msg, file=sys.stderr, flush=True)


# 缓存，避免重复加载
_cached_registry = None


def load_skill_registry():
    """扫描 skills/ 目录，合并所有模块的 SKILL_REGISTRY。
    
    返回: dict[str, callable] — skill_name → handler_fn
    """
    global _cached_registry
    if _cached_registry is not None:
        return _cached_registry

    registry = {}
    skills_dir = os.path.join(os.path.dirname(__file__), "skills")

    for filename in sorted(os.listdir(skills_dir)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue

        module_name = f"skills.{filename[:-3]}"
        try:
            mod = importlib.import_module(module_name)
            mod_registry = getattr(mod, "SKILL_REGISTRY", None)
            if mod_registry and isinstance(mod_registry, dict):
                for skill_name, handler in mod_registry.items():
                    if skill_name in registry:
                        _log(f"[SkillLoader] 警告: skill '{skill_name}' 重复注册，"
                             f"来自 {module_name}，覆盖已有")
                    registry[skill_name] = handler
                _log(f"[SkillLoader] 加载 {module_name}: {list(mod_registry.keys())}")
        except Exception as e:
            _log(f"[SkillLoader] 加载 {module_name} 失败: {e}")

    # 内置 ignore handler
    registry["ignore"] = lambda params, state: {"success": True}

    _log(f"[SkillLoader] 共注册 {len(registry)} 个 skill")
    _cached_registry = registry
    return registry
