#!/usr/bin/env python3
"""
QQ空间动态转发工具 - 入口文件

启动方式:
    python run.py              # 启动 Web 管理界面（默认端口 5000）
    python run.py --port 8080  # 指定端口
    python run.py --no-web     # 仅启动后台调度（无 Web UI）

依赖安装:
    pip install -r requirements.txt
"""
import sys
import os
import argparse
import logging
from pathlib import Path

# 确保 src 在导入路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import load_config, AppConfig
from src.qzone import QzoneClient
from src.sender import OneBotSender
from src.filter import KeywordFilter
from src.db import ForwardDB
from src.scheduler import ForwardScheduler
from src.comment_gen import CommentGenerator
from src.group_import import GroupMemberImporter

# ===== 日志配置 =====
def setup_logging(level=logging.INFO):
    fmt = "%(asctime)s [%(name)s] %(levelname)s %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("qqtranspond.log", encoding="utf-8"),
        ],
    )


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="QQ空间动态转发工具")
    parser.add_argument("--port", type=int, default=5000, help="Web 管理界面端口 (默认 5000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    parser.add_argument("--config", type=str, default="config.yaml", help="配置文件路径")
    parser.add_argument("--no-web", action="store_true", help="仅启动后台调度，不启动 Web 界面")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger("qqtranspond").setLevel(logging.DEBUG)

    logger = logging.getLogger("qqtranspond")

    # ===== 加载配置 =====
    config_path = args.config
    cfg = load_config(config_path)
    logger.info(f"配置加载完成: {config_path}")

    # ===== 初始化组件 =====
    qzone_client = QzoneClient(cfg.qzone.cookies, cfg.qzone.uin)
    sender = OneBotSender(cfg.onebot.host, cfg.onebot.port, cfg.onebot.access_token)
    db = ForwardDB(f"{cfg.data_dir}/forwarded.db")
    comment_gen = CommentGenerator(cfg.actions.comment_templates, cfg.actions.ai)

    scheduler = ForwardScheduler(
        cfg, qzone_client, sender, db,
        comment_gen=comment_gen,
    )

    if args.no_web:
        # 仅后台模式
        logger.info("以无 Web 界面模式启动")
        scheduler.start()
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到退出信号")
            scheduler.stop()
    else:
        # Web 模式
        from src.web.app import create_web_app

        app = create_web_app(
            config_path=config_path,
            config=cfg,
            scheduler=scheduler,
            qzone_client=qzone_client,
            sender=sender,
            db=db,
            comment_gen=comment_gen,
        )

        # 自动启动调度器
        if cfg.qzone.cookies and cfg.monitor_list:
            scheduler.start()

        logger.info(f"Web 管理界面: http://{args.host}:{args.port}")
        logger.info("按 Ctrl+C 退出")

        try:
            app.run(
                host=args.host,
                port=args.port,
                debug=args.debug,
                use_reloader=False,
                threaded=True,  # 多线程处理，避免状态轮询/扫码轮询互相阻塞
            )
        except KeyboardInterrupt:
            pass
        finally:
            scheduler.stop()
            logger.info("工具已停止")


if __name__ == "__main__":
    main()