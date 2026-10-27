"""
配置管理模块 - 加载和验证 YAML 配置文件
"""
import os
import yaml
from typing import List, Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MonitorTarget:
    """监控目标：指定要监控的QQ用户"""
    name: str                # 备注名
    uin: str                 # QQ号
    enabled: bool = True     # 是否启用


@dataclass
class GroupSource:
    """群来源：从群成员自动导入监控列表"""
    group_id: str            # 群号
    name: str = ""           # 群备注名
    enabled: bool = True
    auto_import: bool = True # 是否自动将群成员加入监控


@dataclass
class ForwardTarget:
    """转发目标：转发到群或个人"""
    type: str                # "group" 或 "private"
    id: str                  # 群号或QQ号
    name: str = ""           # 备注名
    enabled: bool = True


@dataclass
class QzoneConfig:
    """QQ空间登录配置"""
    cookies: str = ""        # 浏览器中的 qzone cookies
    uin: str = ""            # 当前登录的QQ号
    poll_interval: int = 60  # 轮询间隔(秒)


@dataclass
class OneBotConfig:
    """OneBot HTTP API 配置"""
    host: str = "127.0.0.1"
    port: int = 5700
    access_token: str = ""


@dataclass
class CommentTemplate:
    """评论模板"""
    content: str             # 模板内容，支持 {nickname} 变量
    weight: int = 1          # 权重（越大越常被选中）


@dataclass
class AIConfig:
    """AI 评论生成配置"""
    enabled: bool = False
    api_url: str = "https://api.deepseek.com/v1/chat/completions"
    api_key: str = ""
    model: str = "deepseek-chat"
    system_prompt: str = "你是一个QQ空间的评论助手。请根据用户的说说的内容，生成一条简短、自然、友好的评论（10-30字）。"
    max_tokens: int = 100
    temperature: float = 0.8


@dataclass
class ActionConfig:
    """对匹配动态执行的操作"""
    forward: bool = True     # 是否转发
    like: bool = False       # 是否点赞
    comment: bool = False    # 是否评论
    comment_mode: str = "template"  # "template" 或 "ai"
    comment_templates: List[CommentTemplate] = field(default_factory=lambda: [
        CommentTemplate(content="说得好！{nickname}"),
        CommentTemplate(content="写的真不错👍"),
    ])
    ai: AIConfig = field(default_factory=AIConfig)


@dataclass
class AppConfig:
    """应用总配置"""
    qzone: QzoneConfig = field(default_factory=QzoneConfig)
    onebot: OneBotConfig = field(default_factory=OneBotConfig)
    keywords: List[str] = field(default_factory=list)
    monitor_list: List[MonitorTarget] = field(default_factory=list)
    group_sources: List[GroupSource] = field(default_factory=list)
    forward_list: List[ForwardTarget] = field(default_factory=list)
    actions: ActionConfig = field(default_factory=ActionConfig)
    data_dir: str = "data"


def load_config(path: str = "config.yaml") -> AppConfig:
    """
    加载YAML配置文件，缺失字段使用默认值
    """
    p = Path(path)
    if not p.exists():
        cfg = AppConfig()
        save_config(cfg, path)
        return cfg

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cfg = AppConfig()

    # Qzone
    qz = raw.get("qzone", {})
    cfg.qzone.cookies = qz.get("cookies", "")
    cfg.qzone.uin = qz.get("uin", "")
    cfg.qzone.poll_interval = qz.get("poll_interval", 60)

    # OneBot
    ob = raw.get("onebot", {})
    cfg.onebot.host = ob.get("host", "127.0.0.1")
    cfg.onebot.port = int(ob.get("port", 5700))
    cfg.onebot.access_token = ob.get("access_token", "")

    # Keywords
    cfg.keywords = raw.get("keywords", [])

    # Monitor list
    for item in raw.get("monitor_list", []):
        cfg.monitor_list.append(MonitorTarget(
            name=item.get("name", ""),
            uin=str(item.get("uin", "")),
            enabled=item.get("enabled", True),
        ))

    # Group sources
    for item in raw.get("group_sources", []):
        cfg.group_sources.append(GroupSource(
            group_id=str(item.get("group_id", "")),
            name=item.get("name", ""),
            enabled=item.get("enabled", True),
            auto_import=item.get("auto_import", True),
        ))

    # Forward list
    for item in raw.get("forward_list", []):
        cfg.forward_list.append(ForwardTarget(
            type=item.get("type", "group"),
            id=str(item.get("id", "")),
            name=item.get("name", ""),
            enabled=item.get("enabled", True),
        ))

    # Actions
    act = raw.get("actions", {})
    cfg.actions.forward = act.get("forward", True)
    cfg.actions.like = act.get("like", False)
    cfg.actions.comment = act.get("comment", False)
    cfg.actions.comment_mode = act.get("comment_mode", "template")

    # Comment templates
    for item in act.get("comment_templates", []):
        cfg.actions.comment_templates.append(CommentTemplate(
            content=item.get("content", ""),
            weight=item.get("weight", 1),
        ))

    # AI config
    ai = act.get("ai", {})
    cfg.actions.ai.enabled = ai.get("enabled", False)
    cfg.actions.ai.api_url = ai.get("api_url", "https://api.deepseek.com/v1/chat/completions")
    cfg.actions.ai.api_key = ai.get("api_key", "")
    cfg.actions.ai.model = ai.get("model", "deepseek-chat")
    cfg.actions.ai.system_prompt = ai.get("system_prompt", cfg.actions.ai.system_prompt)
    cfg.actions.ai.max_tokens = ai.get("max_tokens", 100)
    cfg.actions.ai.temperature = ai.get("temperature", 0.8)

    cfg.data_dir = raw.get("data_dir", "data")

    return cfg


def save_config(cfg: AppConfig, path: str = "config.yaml"):
    """保存配置到 YAML 文件"""
    data = {
        "qzone": {
            "cookies": cfg.qzone.cookies,
            "uin": cfg.qzone.uin,
            "poll_interval": cfg.qzone.poll_interval,
        },
        "onebot": {
            "host": cfg.onebot.host,
            "port": cfg.onebot.port,
            "access_token": cfg.onebot.access_token,
        },
        "keywords": cfg.keywords,
        "monitor_list": [
            {"name": m.name, "uin": m.uin, "enabled": m.enabled}
            for m in cfg.monitor_list
        ],
        "group_sources": [
            {"group_id": g.group_id, "name": g.name, "enabled": g.enabled, "auto_import": g.auto_import}
            for g in cfg.group_sources
        ],
        "forward_list": [
            {"type": f.type, "id": f.id, "name": f.name, "enabled": f.enabled}
            for f in cfg.forward_list
        ],
        "actions": {
            "forward": cfg.actions.forward,
            "like": cfg.actions.like,
            "comment": cfg.actions.comment,
            "comment_mode": cfg.actions.comment_mode,
            "comment_templates": [
                {"content": t.content, "weight": t.weight}
                for t in cfg.actions.comment_templates
            ],
            "ai": {
                "enabled": cfg.actions.ai.enabled,
                "api_url": cfg.actions.ai.api_url,
                "api_key": cfg.actions.ai.api_key,
                "model": cfg.actions.ai.model,
                "system_prompt": cfg.actions.ai.system_prompt,
                "max_tokens": cfg.actions.ai.max_tokens,
                "temperature": cfg.actions.ai.temperature,
            },
        },
        "data_dir": cfg.data_dir,
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)