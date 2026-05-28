"""
模型工厂：从 config.yaml 读取模型配置，动态实例化 LangChain Chat 模型。

config.yaml 中每个模型条目格式：
  - name: my-model
    use: langchain_openai:ChatOpenAI   # module:ClassName
    model: gpt-4o
    api_key: $MY_API_KEY               # $ 开头从环境变量读取，否则直接使用
    base_url: https://...
    temperature: 0.7
    max_tokens: 4096
    ...                                # 其余字段直接透传给构造函数
"""

import importlib
import os
from pathlib import Path
from typing import Any

import yaml
from langchain_core.language_models import BaseChatModel

# 不传给模型构造函数的内部字段
_RESERVED_KEYS = {"name", "use", "display_name", "supports_vision", "supports_thinking"}


def _resolve_env(value: Any) -> Any:
    """将 $VAR_NAME 替换为对应环境变量的值"""
    if isinstance(value, str) and value.startswith("$"):
        env_name = value[1:]
        resolved = os.getenv(env_name, "")
        if not resolved:
            raise EnvironmentError(f"环境变量 {env_name!r} 未设置，无法初始化模型")
        return resolved
    return value


def _import_class(use: str) -> type:
    """解析 'module:ClassName' 并返回类对象"""
    if ":" not in use:
        raise ValueError(f"use 字段格式应为 'module:ClassName'，当前值：{use!r}")
    module_path, class_name = use.rsplit(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls


def _build_model(entry: dict) -> BaseChatModel:
    """根据单个模型配置条目实例化模型"""
    use = entry.get("use")
    if not use:
        raise ValueError(f"模型 {entry.get('name')!r} 缺少 use 字段")

    cls = _import_class(use)

    kwargs = {
        k: _resolve_env(v)
        for k, v in entry.items()
        if k not in _RESERVED_KEYS
    }
    return cls(**kwargs)


def load_model(name: str | None = None, yaml_path: str | Path | None = None) -> BaseChatModel:
    """
    从 config.yaml 加载指定名称的模型。

    Args:
        name: 模型 name。None 时读取 CHOREO_MODEL_NAME 环境变量，
              再回退到 yaml 的 active_model 字段。
        yaml_path: yaml 文件路径，默认为项目根目录的 config.yaml。

    Returns:
        已实例化的 BaseChatModel 对象。
    """
    if yaml_path is None:
        yaml_path = Path(__file__).parent.parent / "config.yaml"

    with open(yaml_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    target = name or os.getenv("CHOREO_MODEL_NAME") or cfg.get("active_model", "")
    if not target:
        raise ValueError("未指定模型名，请设置 active_model 或 CHOREO_MODEL_NAME")

    models: list[dict] = cfg.get("models", [])
    entry = next((m for m in models if m.get("name") == target), None)
    if entry is None:
        available = [m.get("name") for m in models]
        raise ValueError(f"找不到模型 {target!r}，可用：{available}")

    return _build_model(entry)
