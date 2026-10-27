"""
调度监控模块
定时轮询指定用户的 QQ 空间，过滤关键词后执行转发/点赞/评论
"""
import time
import logging
import threading
from typing import Callable, Optional
from datetime import datetime

from .config import AppConfig
from .qzone import QzoneClient
from .filter import KeywordFilter
from .sender import OneBotSender
from .db import ForwardDB
from .comment_gen import CommentGenerator
from .group_import import GroupMemberImporter

logger = logging.getLogger("qqtranspond.scheduler")


class ForwardScheduler:
    """
    转发调度器
    按配置轮询监控列表中的 QQ 空间，关键词匹配后执行配置的动作
    """

    def __init__(
        self,
        config: AppConfig,
        qzone_client: QzoneClient,
        sender: OneBotSender,
        db: ForwardDB,
        comment_gen: Optional[CommentGenerator] = None,
        on_action: Optional[Callable[[dict], None]] = None,
    ):
        """
        :param config:       应用配置
        :param qzone_client: Qzone API 客户端
        :param sender:       OneBot 消息发送器
        :param db:           已转发记录数据库
        :param comment_gen:  评论生成器（可选）
        :param on_action:    可选回调，执行动作时触发（用于 Web UI 通知）
        """
        self.config = config
        self.qzone = qzone_client
        self.sender = sender
        self.db = db
        self.comment_gen = comment_gen
        self.on_action = on_action

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stats = {
            "total_checked": 0,
            "total_matched": 0,
            "total_forwarded": 0,
            "total_liked": 0,
            "total_commented": 0,
            "start_time": None,
            "last_check_time": None,
        }
        self._filter = KeywordFilter(config.keywords)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict:
        return {**self._stats}

    def start(self):
        """启动调度器（后台线程）"""
        if self._running:
            logger.warning("调度器已在运行中")
            return

        if not self.config.qzone.cookies:
            logger.error("未配置 Qzone Cookies，无法启动")
            return

        # 启动前同步群来源
        self._sync_group_members()

        if not self.config.monitor_list:
            logger.warning("监控列表为空，调度器启动但不会做任何事")
        if not self.config.forward_list and not self.config.actions.like and not self.config.actions.comment:
            logger.warning("未配置任何动作（转发/点赞/评论），调度器启动但不会做任何事")

        self._running = True
        self._stats["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("调度器已启动")

    def stop(self):
        """停止调度器"""
        self._running = False
        logger.info("调度器已停止")

    def _sync_group_members(self):
        """启动时同步群来源成员到监控列表"""
        if not self.config.group_sources:
            return
        if not self.sender.check_online():
            logger.warning("OneBot 不在线，跳过群成员同步")
            return

        try:
            importer = GroupMemberImporter(self.sender)
            added = importer.sync_group_sources(self.config)
            if added > 0:
                logger.info(f"群成员同步完成，新增 {added} 个监控目标")
        except Exception as e:
            logger.error(f"群成员同步失败: {e}")

    def _run_loop(self):
        """主循环：轮询所有监控目标"""
        interval = max(self.config.qzone.poll_interval, 15)

        while self._running:
            try:
                self._check_all()
            except Exception as e:
                logger.error(f"轮询异常: {e}", exc_info=True)

            self._stats["last_check_time"] = datetime.now().strftime("%H:%M:%S")

            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)

    def _check_all(self):
        """检查所有启用的监控目标"""
        # 热加载关键词
        self._filter = KeywordFilter(self.config.keywords)

        for target in self.config.monitor_list:
            if not self._running:
                break
            if not target.enabled:
                continue

            try:
                self._check_target(target.uin, target.name)
            except Exception as e:
                logger.error(f"检查 {target.name}({target.uin}) 失败: {e}")

    def _check_target(self, target_uin: str, target_name: str):
        """检查单个目标用户的最新说说"""
        posts = self.qzone.fetch_shuoshuo(target_uin, num=5, pos=0)
        if not posts:
            return

        # 获取用户昵称
        try:
            user_info = self.qzone.get_user_info(target_uin)
            nickname = user_info.get("nickname", "") if user_info else target_name
        except Exception:
            nickname = target_name

        for post in posts:
            if not self._running:
                break

            tid = post.get("tid", "")
            # 已处理则跳过
            if not tid or self.db.is_forwarded(tid):
                continue

            self._stats["total_checked"] += 1
            content = post.get("content", "") or ""

            # 关键词过滤
            if self._filter.is_active and not self._filter.match(content):
                continue

            self._stats["total_matched"] += 1
            post["nickname"] = nickname

            # ===== 执行动作 =====
            action_results = {}

            # 1. 转发
            if self.config.actions.forward and self.config.forward_list:
                message = KeywordFilter.format_content(post)
                success_count = self.sender.send_to_all(self.config.forward_list, message)
                self._stats["total_forwarded"] += 1
                action_results["forward"] = {
                    "success": success_count > 0,
                    "targets": len(self.config.forward_list),
                    "sent": success_count,
                }

            # 2. 点赞
            if self.config.actions.like:
                like_ok = self.qzone.like_shuoshuo(target_uin, tid)
                self._stats["total_liked"] += 1
                action_results["like"] = {"success": like_ok}

            # 3. 评论
            if self.config.actions.comment and self.comment_gen:
                comment_text = self.comment_gen.generate(
                    post, mode=self.config.actions.comment_mode
                )
                if comment_text:
                    comment_ok = self.qzone.comment_shuoshuo(target_uin, tid, comment_text)
                    self._stats["total_commented"] += 1
                    action_results["comment"] = {"success": comment_ok, "text": comment_text}
                else:
                    action_results["comment"] = {"success": False, "text": ""}

            # 标记已处理
            self.db.mark_forwarded(tid, target_uin, content)

            # 日志
            actions_done = [k for k, v in action_results.items() if v.get("success")]
            logger.info(
                f"动作完成: [{target_name}/{nickname}] "
                f"内容={content[:60]}... "
                f"动作=[{', '.join(actions_done) or '无'}]"
            )

            # 回调通知
            if self.on_action:
                try:
                    self.on_action({
                        "tid": tid,
                        "uin": target_uin,
                        "name": target_name,
                        "nickname": nickname,
                        "content": content[:200],
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "actions": action_results,
                    })
                except Exception:
                    pass