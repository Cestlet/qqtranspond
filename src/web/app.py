"""
Web 管理界面
提供浏览器可访问的配置管理、状态查看、手动操作等功能
"""
import json
import os
import secrets
import logging
import threading
import time
from typing import Optional
from pathlib import Path

from flask import Flask, render_template, request, jsonify

from ..config import (
    AppConfig, MonitorTarget, ForwardTarget, GroupSource,
    CommentTemplate, AIConfig, ActionConfig,
    load_config, save_config,
)
from ..qzone import QzoneClient
from ..sender import OneBotSender
from ..filter import KeywordFilter
from ..db import ForwardDB
from ..scheduler import ForwardScheduler
from ..comment_gen import CommentGenerator
from ..group_import import GroupMemberImporter
from ..qr_login import QRLogin

logger = logging.getLogger("qqtranspond.web")


def create_web_app(
    config_path: str = "config.yaml",
    config: Optional[AppConfig] = None,
    scheduler: Optional[ForwardScheduler] = None,
    qzone_client: Optional[QzoneClient] = None,
    sender: Optional[OneBotSender] = None,
    db: Optional[ForwardDB] = None,
    comment_gen: Optional[CommentGenerator] = None,
) -> Flask:
    """
    创建 Flask Web 应用
    """
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent.parent.parent / "templates"),
        static_folder=str(Path(__file__).parent.parent.parent / "static"),
    )
    app.config["SECRET_KEY"] = os.environ.get("QQTRANSPOND_SECRET_KEY") or secrets.token_hex(32)

    # 存储引用
    app.extensions["config_path"] = config_path
    app.extensions["config"] = config
    app.extensions["scheduler"] = scheduler
    app.extensions["qzone_client"] = qzone_client
    app.extensions["sender"] = sender
    app.extensions["db"] = db
    app.extensions["comment_gen"] = comment_gen

    # ===================== 页面路由 =====================

    @app.route("/")
    def index():
        cfg = _get_config(app)
        sched = app.extensions.get("scheduler")
        db = app.extensions.get("db")
        return render_template("index.html",
            config=cfg,
            scheduler_running=sched.is_running if sched else False,
            scheduler_stats=sched.stats if sched else {},
            forwarded_count=db.get_forwarded_count() if db else 0,
            recent_forwarded=db.get_recent(10) if db else [],
        )

    # ===================== 状态 API =====================

    @app.route("/api/status")
    def api_status():
        cfg = _get_config(app)
        sched = app.extensions.get("scheduler")
        sender = app.extensions.get("sender")
        db = app.extensions.get("db")

        onebot_online = sender.check_online() if sender else False
        qzone_configured = bool(cfg.qzone.cookies and cfg.qzone.uin)

        return jsonify({
            "scheduler": {
                "running": sched.is_running if sched else False,
                "stats": sched.stats if sched else {},
            },
            "onebot_online": onebot_online,
            "qzone_configured": qzone_configured,
            "monitor_count": len([m for m in cfg.monitor_list if m.enabled]),
            "group_source_count": len([g for g in cfg.group_sources if g.enabled]),
            "forward_count": len([f for f in cfg.forward_list if f.enabled]),
            "keyword_count": len(cfg.keywords),
            "forwarded_total": db.get_forwarded_count() if db else 0,
            "actions": {
                "forward": cfg.actions.forward,
                "like": cfg.actions.like,
                "comment": cfg.actions.comment,
                "comment_mode": cfg.actions.comment_mode,
            },
        })

    # ===================== 配置 API =====================

    @app.route("/api/config", methods=["GET"])
    def api_get_config():
        cfg = _get_config(app)
        return jsonify({
            "qzone": {
                "cookies": _mask_cookies(cfg.qzone.cookies),
                "uin": cfg.qzone.uin,
                "poll_interval": cfg.qzone.poll_interval,
            },
            "onebot": {
                "host": cfg.onebot.host,
                "port": cfg.onebot.port,
                "access_token": _mask_token(cfg.onebot.access_token),
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
                    "api_key": _mask_token(cfg.actions.ai.api_key),
                    "model": cfg.actions.ai.model,
                    "system_prompt": cfg.actions.ai.system_prompt,
                    "max_tokens": cfg.actions.ai.max_tokens,
                    "temperature": cfg.actions.ai.temperature,
                },
            },
        })

    @app.route("/api/config", methods=["POST"])
    def api_save_config():
        data = request.get_json(force=True)
        cfg = _get_config(app)

        if "qzone" in data:
            qz = data["qzone"]
            if "cookies" in qz and not qz["cookies"].startswith("***"):
                cfg.qzone.cookies = qz["cookies"]
            if "uin" in qz:
                cfg.qzone.uin = str(qz["uin"])
            if "poll_interval" in qz:
                cfg.qzone.poll_interval = int(qz["poll_interval"])

        if "onebot" in data:
            ob = data["onebot"]
            if "host" in ob:
                cfg.onebot.host = ob["host"]
            if "port" in ob:
                cfg.onebot.port = int(ob["port"])
            if "access_token" in ob and not ob["access_token"].startswith("***"):
                cfg.onebot.access_token = ob["access_token"]

        if "keywords" in data:
            cfg.keywords = data["keywords"]

        if "monitor_list" in data:
            cfg.monitor_list = [
                MonitorTarget(name=m.get("name", ""), uin=str(m.get("uin", "")), enabled=m.get("enabled", True))
                for m in data["monitor_list"]
            ]

        if "group_sources" in data:
            cfg.group_sources = [
                GroupSource(group_id=str(g.get("group_id", "")), name=g.get("name", ""),
                            enabled=g.get("enabled", True), auto_import=g.get("auto_import", True))
                for g in data["group_sources"]
            ]

        if "forward_list" in data:
            cfg.forward_list = [
                ForwardTarget(type=f.get("type", "group"), id=str(f.get("id", "")),
                              name=f.get("name", ""), enabled=f.get("enabled", True))
                for f in data["forward_list"]
            ]

        if "actions" in data:
            act = data["actions"]
            cfg.actions.forward = act.get("forward", True)
            cfg.actions.like = act.get("like", False)
            cfg.actions.comment = act.get("comment", False)
            cfg.actions.comment_mode = act.get("comment_mode", "template")

            if "comment_templates" in act:
                cfg.actions.comment_templates = [
                    CommentTemplate(content=t.get("content", ""), weight=t.get("weight", 1))
                    for t in act["comment_templates"]
                ]

            if "ai" in act:
                ai = act["ai"]
                if "enabled" in ai:
                    cfg.actions.ai.enabled = ai["enabled"]
                if "api_url" in ai:
                    cfg.actions.ai.api_url = ai["api_url"]
                if "api_key" in ai and not ai["api_key"].startswith("***"):
                    cfg.actions.ai.api_key = ai["api_key"]
                if "model" in ai:
                    cfg.actions.ai.model = ai["model"]
                if "system_prompt" in ai:
                    cfg.actions.ai.system_prompt = ai["system_prompt"]
                if "max_tokens" in ai:
                    cfg.actions.ai.max_tokens = int(ai["max_tokens"])
                if "temperature" in ai:
                    cfg.actions.ai.temperature = float(ai["temperature"])

        save_config(cfg, app.extensions["config_path"])
        app.extensions["config"] = cfg

        # 重建评论生成器
        _rebuild_comment_gen(app, cfg)

        # 重启调度器
        sched = app.extensions.get("scheduler")
        if sched and sched.is_running:
            threading.Thread(target=_restart_scheduler, args=(sched, cfg, app), daemon=True).start()

        return jsonify({"success": True, "message": "配置已保存"})

    # ===================== 调度器控制 =====================

    @app.route("/api/scheduler/start", methods=["POST"])
    def api_scheduler_start():
        sched = app.extensions.get("scheduler")
        if not sched:
            return jsonify({"success": False, "message": "调度器未初始化"}), 400

        cfg = _get_config(app)
        if not cfg.qzone.cookies or not cfg.qzone.uin:
            return jsonify({"success": False, "message": "请先完成 QQ 空间扫码登录（未配置 Cookies）"}), 400
        if not any(m.enabled for m in cfg.monitor_list):
            return jsonify({"success": False, "message": "监控列表为空，请先添加监控目标或群来源"}), 400

        # 保存配置后再启动
        _save_current_config(app)
        sched.start()
        if not sched.is_running:
            return jsonify({"success": False, "message": "调度器启动失败，请检查配置"}), 400
        return jsonify({"success": True, "message": "调度器已启动"})

    @app.route("/api/scheduler/stop", methods=["POST"])
    def api_scheduler_stop():
        sched = app.extensions.get("scheduler")
        if not sched:
            return jsonify({"success": False, "message": "调度器未初始化"}), 400
        sched.stop()
        return jsonify({"success": True, "message": "调度器已停止"})

    # ===================== 测试功能 =====================

    @app.route("/api/test/onebot", methods=["POST"])
    def api_test_onebot():
        sender = app.extensions.get("sender")
        if not sender:
            return jsonify({"success": False, "message": "发送器未初始化"}), 400
        online = sender.check_online()
        info = sender.get_login_info() if online else None
        return jsonify({
            "success": online,
            "message": "连接成功" if online else "无法连接到 OneBot 服务",
            "data": info,
        })

    @app.route("/api/test/qzone", methods=["POST"])
    def api_test_qzone():
        cfg = _get_config(app)
        qzone = app.extensions.get("qzone_client")
        if not qzone:
            return jsonify({"success": False, "message": "Qzone 客户端未初始化"}), 400
        if not cfg.qzone.uin:
            return jsonify({"success": False, "message": "未配置 QQ 号"}), 400
        info = qzone.get_user_info(cfg.qzone.uin)
        if info:
            return jsonify({"success": True, "message": f"获取成功: {info.get('nickname', '')}", "data": info})
        else:
            return jsonify({"success": False, "message": "获取用户信息失败，请检查 Cookies 是否有效"})

    @app.route("/api/test/fetch", methods=["POST"])
    def api_test_fetch():
        data = request.get_json(force=True)
        target_uin = data.get("uin", "")
        if not target_uin:
            return jsonify({"success": False, "message": "请提供 QQ 号"}), 400
        qzone = app.extensions.get("qzone_client")
        if not qzone:
            return jsonify({"success": False, "message": "Qzone 客户端未初始化"}), 400
        posts = qzone.fetch_shuoshuo(target_uin, num=3)
        return jsonify({"success": True, "posts": posts, "count": len(posts)})

    @app.route("/api/test/comment", methods=["POST"])
    def api_test_comment():
        """测试评论生成"""
        data = request.get_json(force=True)
        mode = data.get("mode", "template")
        content = data.get("content", "测试内容")
        nickname = data.get("nickname", "朋友")

        cfg = _get_config(app)
        gen = CommentGenerator(cfg.actions.comment_templates, cfg.actions.ai)
        post = {"content": content, "nickname": nickname, "create_time": "2024-01-01 12:00:00"}
        result = gen.generate(post, mode=mode)
        return jsonify({
            "success": bool(result),
            "comment": result or "生成失败",
            "mode": mode,
        })

    # ===================== 群成员导入 =====================

    @app.route("/api/group/members", methods=["POST"])
    def api_group_members():
        """获取群成员列表"""
        data = request.get_json(force=True)
        group_id = data.get("group_id", "")
        if not group_id:
            return jsonify({"success": False, "message": "请提供群号"}), 400

        sender = app.extensions.get("sender")
        if not sender:
            return jsonify({"success": False, "message": "发送器未初始化"}), 400

        if not sender.check_online():
            return jsonify({"success": False, "message": "OneBot 不在线"}), 400

        importer = GroupMemberImporter(sender)
        members = importer.fetch_members(group_id)
        if members is None:
            return jsonify({"success": False, "message": "获取群成员失败"}), 400

        # 返回前 100 个成员
        return jsonify({
            "success": True,
            "members": members[:100],
            "total": len(members),
        })

    @app.route("/api/group/import", methods=["POST"])
    def api_group_import():
        """将群成员导入到监控列表"""
        data = request.get_json(force=True)
        group_id = data.get("group_id", "")
        if not group_id:
            return jsonify({"success": False, "message": "请提供群号"}), 400

        cfg = _get_config(app)
        sender = app.extensions.get("sender")
        if not sender:
            return jsonify({"success": False, "message": "发送器未初始化"}), 400

        importer = GroupMemberImporter(sender)
        members = importer.fetch_members(group_id)
        if members is None:
            return jsonify({"success": False, "message": "获取群成员失败"}), 400

        added = importer.import_to_monitor_list(cfg, group_id, members)
        save_config(cfg, app.extensions["config_path"])

        return jsonify({
            "success": True,
            "added": added,
            "total_members": len(members),
            "message": f"成功导入 {added} 个新监控目标",
        })

    # ===================== 转发记录 =====================

    @app.route("/api/forwarded", methods=["GET"])
    def api_forwarded():
        db = app.extensions.get("db")
        if not db:
            return jsonify({"success": False, "message": "数据库未初始化"}), 400
        limit = request.args.get("limit", 20, type=int)
        records = db.get_recent(limit)
        return jsonify({
            "success": True,
            "records": records,
            "total": db.get_forwarded_count(),
        })

    # ===================== QR 扫码登录 =====================

    # 存储当前登录会话（内存中，仅一个用户）
    qr_login_instance = {"login": None}

    @app.route("/api/login/qrcode", methods=["POST"])
    def api_login_qrcode():
        """获取登录二维码"""
        qr = QRLogin()
        img_data = qr.get_qrcode()
        if img_data is None:
            return jsonify({"success": False, "message": "获取二维码失败"}), 500

        import base64
        b64 = base64.b64encode(img_data).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        qr_login_instance["login"] = qr
        return jsonify({
            "success": True,
            "qrcode": data_uri,
        })

    @app.route("/api/login/poll", methods=["GET"])
    def api_login_poll():
        """轮询登录状态"""
        qr = qr_login_instance.get("login")
        if not qr:
            return jsonify({"success": False, "message": "未开始扫码登录"}), 400

        result = qr.poll_login()

        if result.get("status") == "success" and result.get("cookies"):
            # 自动保存配置
            cfg = _get_config(app)
            cfg.qzone.cookies = result["cookies"]
            cfg.qzone.uin = result.get("final_uin") or result.get("uin", "")
            save_config(cfg, app.extensions["config_path"])
            app.extensions["config"] = cfg

            # 重建调度器（含新的 Qzone 客户端）
            _rebuild_scheduler(app, cfg)

            # 尝试获取昵称用于展示
            nickname = ""
            qzone = app.extensions.get("qzone_client")
            if qzone:
                try:
                    info = qzone.get_user_info(cfg.qzone.uin)
                    if info:
                        nickname = info.get("nickname", "")
                except Exception:
                    pass

            return jsonify({
                "success": True,
                "logged_in": True,
                "uin": cfg.qzone.uin,
                "nickname": nickname,
                "message": "登录成功，配置已自动保存",
            })

        return jsonify({
            "success": True,
            "logged_in": False,
            "status": result.get("status", "unknown"),
            "message": result.get("message", ""),
        })

    @app.route("/api/login/status", methods=["GET"])
    def api_login_status():
        """获取当前登录态"""
        cfg = _get_config(app)
        qzone = app.extensions.get("qzone_client")
        if cfg.qzone.cookies and cfg.qzone.uin:
            # 验证 cookies 是否有效
            info = None
            if qzone:
                try:
                    info = qzone.get_user_info(cfg.qzone.uin)
                except Exception:
                    pass
            return jsonify({
                "logged_in": bool(info),
                "uin": cfg.qzone.uin,
                "nickname": info.get("nickname", "") if info else "",
                "message": f"已登录: {info.get('nickname', '')}" if info else "Cookies 可能已过期",
            })
        return jsonify({"logged_in": False, "uin": "", "nickname": "", "message": "未登录"})

    # ===================== 一键启动 =====================

    @app.route("/api/quickstart", methods=["POST"])
    def api_quickstart():
        """
        一键启动：自动检查前置条件 → 导入群成员 → 保存配置 → 启动调度器
        前置条件：已完成扫码登录，已配置 OneBot
        """
        cfg = _get_config(app)
        sched = app.extensions.get("scheduler")
        sender = app.extensions.get("sender")

        # 检查前置条件
        if not cfg.qzone.cookies or not cfg.qzone.uin:
            return jsonify({"success": False, "step": "login", "message": "请先完成 QQ 空间扫码登录（步骤 1）"})

        if not sender or not sender.check_online():
            return jsonify({"success": False, "step": "onebot", "message": "OneBot 未连接，请先启动 OneBot 客户端（步骤 2）"})

        # 从群来源导入成员
        if cfg.group_sources:
            try:
                importer = GroupMemberImporter(sender)
                added = importer.sync_group_sources(cfg)
                if added > 0:
                    save_config(cfg, app.extensions["config_path"])
                    logger.info(f"一键启动: 自动导入 {added} 个群成员")
            except Exception as e:
                logger.warning(f"一键启动: 群成员导入失败 {e}")

        # 检查监控列表
        if not any(m.enabled for m in cfg.monitor_list):
            return jsonify({
                "success": False, "step": "monitor",
                "message": "监控列表为空，请先添加群来源或手动添加监控目标"
            })

        # 检查动作配置
        if not cfg.forward_list and not cfg.actions.like and not cfg.actions.comment:
            return jsonify({
                "success": False, "step": "action",
                "message": "未配置任何动作（转发/点赞/评论），请先在「动作」或「转发列表」中配置"
            })

        # 启动调度器
        if sched and not sched.is_running:
            sched.start()
            if not sched.is_running:
                return jsonify({
                    "success": False, "step": "scheduler",
                    "message": "调度器启动失败，请检查配置"
                })
            return jsonify({
                "success": True,
                "message": "一键启动成功！调度器已运行",
                "stats": sched.stats,
            })
        elif sched and sched.is_running:
            return jsonify({"success": True, "message": "调度器已在运行中", "stats": sched.stats})
        else:
            return jsonify({"success": False, "step": "scheduler", "message": "调度器未初始化"})

    # ===================== 返回 App =====================

    return app


# ===================== 辅助函数 =====================

def _get_config(app: Flask) -> AppConfig:
    cfg = app.extensions.get("config")
    if cfg is None:
        cfg = load_config(app.extensions["config_path"])
        app.extensions["config"] = cfg
    return cfg


def _save_current_config(app: Flask):
    """保存当前内存中的配置到文件"""
    cfg = _get_config(app)
    save_config(cfg, app.extensions["config_path"])


def _rebuild_comment_gen(app: Flask, cfg: AppConfig):
    """重建评论生成器"""
    gen = CommentGenerator(cfg.actions.comment_templates, cfg.actions.ai)
    app.extensions["comment_gen"] = gen


def _mask_cookies(cookies: str) -> str:
    if not cookies:
        return ""
    return cookies[:20] + "***" if len(cookies) > 20 else cookies


def _mask_token(token: str) -> str:
    if not token:
        return ""
    return token[:6] + "***" if len(token) > 6 else token


def _restart_scheduler(sched: ForwardScheduler, cfg: AppConfig, app: Flask):
    """重启调度器（后台执行）"""
    try:
        sched.stop()
        time.sleep(1)

        qzone = QzoneClient(cfg.qzone.cookies, cfg.qzone.uin)
        sender = OneBotSender(cfg.onebot.host, cfg.onebot.port, cfg.onebot.access_token)
        db = ForwardDB(f"{cfg.data_dir}/forwarded.db")
        comment_gen = CommentGenerator(cfg.actions.comment_templates, cfg.actions.ai)

        new_sched = ForwardScheduler(cfg, qzone, sender, db, comment_gen=comment_gen)

        app.extensions["qzone_client"] = qzone
        app.extensions["sender"] = sender
        app.extensions["db"] = db
        app.extensions["comment_gen"] = comment_gen
        app.extensions["scheduler"] = new_sched

        new_sched.start()
        logger.info("调度器已重启并应用新配置")
    except Exception as e:
        logger.error(f"重启调度器失败: {e}", exc_info=True)


def _rebuild_scheduler(app: Flask, cfg: AppConfig):
    """重建调度器组件（不阻塞，用于扫码登录后重建）"""
    try:
        # 停止旧的
        old = app.extensions.get("scheduler")
        if old and old.is_running:
            old.stop()
            time.sleep(0.5)

        db = ForwardDB(f"{cfg.data_dir}/forwarded.db")
        sender = OneBotSender(cfg.onebot.host, cfg.onebot.port, cfg.onebot.access_token)
        comment_gen = CommentGenerator(cfg.actions.comment_templates, cfg.actions.ai)
        qzone = QzoneClient(cfg.qzone.cookies, cfg.qzone.uin)

        new_sched = ForwardScheduler(cfg, qzone, sender, db, comment_gen=comment_gen)

        app.extensions["qzone_client"] = qzone
        app.extensions["sender"] = sender
        app.extensions["db"] = db
        app.extensions["comment_gen"] = comment_gen
        app.extensions["scheduler"] = new_sched

        logger.info("调度器组件已重建")
    except Exception as e:
        logger.error(f"重建调度器失败: {e}", exc_info=True)