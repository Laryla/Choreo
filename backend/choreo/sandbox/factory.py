"""
沙箱工厂：从 config.yaml 读取沙箱配置，动态实例化对应的 BaseSandbox 实现。

config.yaml 中沙箱配置格式：
  active_sandbox: local-dev

  sandboxes:
    - name: local-dev
      provider: local
      workspace_dir: ./sandbox
      timeout: 120
      idle_timeout: 1800
    - name: cloud-daytona
      provider: daytona
      api_key: $DAYTONA_API_KEY
      api_url: $DAYTONA_API_URL
"""

import importlib
import os
from pathlib import Path
from typing import Any

import yaml

from choreo.model_factory import _resolve_env
from choreo.sandbox.base import BaseSandbox

# provider 名称 → 实现类的 "module:ClassName" 字符串（延迟 import）
PROVIDERS: dict[str, str] = {
    "local": "choreo.sandbox.providers.local:LocalSandbox",
    "docker": "choreo.sandbox.providers.docker:DockerSandbox",
    "llm-sandbox": "choreo.sandbox.providers.llm_sandbox:LLMSandboxAdapter",
    "daytona": "choreo.sandbox.providers.daytona:DaytonaSandboxAdapter",
    "aios": "choreo.sandbox.providers.aios:AiosSandbox",
}

# 不传给沙箱构造函数的内部保留字段
_RESERVED_KEYS = {"name", "provider", "idle_timeout"}

def _load_yaml(yaml_path: str | Path | None) -> dict:
    """yaml_path 不为 None 时直接读文件（测试用），否则从 settings 取。"""
    if yaml_path is not None:
        with open(yaml_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    from choreo.config import settings
    _base = Path(__file__).parents[2]
    return {
        "active_sandbox": settings.ACTIVE_SANDBOX,
        "sandboxes": settings.SANDBOXES,
        "output_dir": str((_base / settings.OUTPUT_DIR).resolve()) if settings.OUTPUT_DIR else None,
    }


def _import_provider_class(provider: str) -> type:
    """解析 PROVIDERS 中的 'module:ClassName' 并动态 import，未安装时给出友好错误。"""
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(
            f"未知的 sandbox provider: {provider!r}，"
            f"支持的 provider：{list(PROVIDERS)}"
        )

    module_path, class_name = spec.rsplit(":", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"sandbox provider {provider!r} 对应的模块 {module_path!r} 无法导入。"
            f"请先安装所需依赖包。\n原始错误：{exc}"
        ) from exc

    return getattr(module, class_name)


def get_active_sandbox_config(yaml_path: str | Path | None = None) -> dict:
    """
    返回 active sandbox 的完整配置条目（含 idle_timeout 等所有字段）。

    名称解析顺序：
      1. 环境变量 CHOREO_SANDBOX_NAME
      2. config.yaml 的 active_sandbox 字段

    Raises:
        ValueError: 找不到对应的 sandbox 配置条目。
    """
    cfg = _load_yaml(yaml_path)
    target = os.getenv("CHOREO_SANDBOX_NAME") or cfg.get("active_sandbox", "")
    if not target:
        raise ValueError(
            "未指定 sandbox 名称，请设置 active_sandbox 或环境变量 CHOREO_SANDBOX_NAME"
        )

    sandboxes: list[dict] = cfg.get("sandboxes", [])
    entry = next((s for s in sandboxes if s.get("name") == target), None)
    if entry is None:
        available = [s.get("name") for s in sandboxes]
        raise ValueError(
            f"找不到 sandbox {target!r}，config.yaml 中可用：{available}"
        )

    return entry


def sandbox_factory(
    name: str | None = None,
    yaml_path: str | Path | None = None,
    extra_kwargs: dict[str, Any] | None = None,
) -> BaseSandbox:
    """
    根据 config.yaml 创建并返回对应的 BaseSandbox 实例。

    名称解析顺序（当 name=None 时）：
      1. 环境变量 CHOREO_SANDBOX_NAME
      2. config.yaml 的 active_sandbox 字段

    Args:
        name:      sandbox 名称（对应 sandboxes[].name）；None 时自动解析。
        yaml_path: config.yaml 路径；None 时使用默认路径。

    Returns:
        已实例化的 BaseSandbox 子类对象（尚未 start）。

    Raises:
        ValueError:      找不到对应配置或 provider 未知。
        EnvironmentError: 需要的环境变量未设置（$VAR 替换失败）。
        ImportError:     provider 依赖包未安装。
    """
    cfg = _load_yaml(yaml_path)

    target = name or os.getenv("CHOREO_SANDBOX_NAME") or cfg.get("active_sandbox", "")
    if not target:
        raise ValueError(
            "未指定 sandbox 名称，请设置 active_sandbox 或环境变量 CHOREO_SANDBOX_NAME"
        )

    sandboxes: list[dict] = cfg.get("sandboxes", [])
    entry = next((s for s in sandboxes if s.get("name") == target), None)
    if entry is None:
        available = [s.get("name") for s in sandboxes]
        raise ValueError(
            f"找不到 sandbox {target!r}，config.yaml 中可用：{available}"
        )

    provider = entry.get("provider")
    if not provider:
        raise ValueError(
            f"sandbox {target!r} 缺少 provider 字段"
        )

    cls = _import_provider_class(provider)

    # 过滤保留字段，对 $VAR 值进行环境变量替换
    kwargs: dict[str, Any] = {
        k: _resolve_env(v)
        for k, v in entry.items()
        if k not in _RESERVED_KEYS
    }

    # 注入根级别的 skills_dir / output_dir（sandbox entry 未显式指定时才注入）
    from choreo.config import settings
    if "skills_dir" not in kwargs and settings.SKILLS_DIR:
        _base = Path(__file__).parents[2]
        kwargs["skills_dir"] = str((_base / settings.SKILLS_DIR).resolve())
    if "output_dir" not in kwargs and settings.OUTPUT_DIR:
        _base = Path(__file__).parents[2]
        kwargs["output_dir"] = str((_base / settings.OUTPUT_DIR).resolve())

    if extra_kwargs:
        kwargs.update(extra_kwargs)

    return cls(**kwargs)
