"""
群成员导入模块
通过 OneBot API 获取群成员列表，并自动添加到监控列表
"""
import logging
from typing import List, Optional, Set

from .config import GroupSource, MonitorTarget, AppConfig
from .sender import OneBotSender

logger = logging.getLogger("qqtranspond.group_import")


class GroupMemberImporter:
    """群成员导入器"""

    def __init__(self, sender: OneBotSender):
        self.sender = sender

    def fetch_members(self, group_id: str) -> Optional[List[dict]]:
        """
        从 OneBot 获取群成员列表

        :param group_id: 群号
        :return: 成员列表 [{"user_id": xxx, "nickname": "xxx", ...}, ...]
        """
        members = self.sender.get_group_member_list(group_id)
        if members is None:
            logger.error(f"获取群 {group_id} 成员列表失败")
            return None

        logger.info(f"获取群 {group_id} 成员: {len(members)} 人")
        return members

    def import_to_monitor_list(
        self,
        config: AppConfig,
        group_id: str,
        members: List[dict],
    ) -> int:
        """
        将群成员导入到监控列表（去重）

        :param config:   应用配置（会被修改）
        :param group_id: 群号
        :param members:  成员列表
        :return:         新增的监控人数
        """
        existing_uins: Set[str] = {m.uin for m in config.monitor_list}
        added = 0

        # 获取群名称
        group_name = ""
        for gs in config.group_sources:
            if gs.group_id == group_id:
                group_name = gs.name or f"群{group_id}"
                break

        for member in members:
            user_id = str(member.get("user_id", ""))
            if not user_id:
                continue

            # 跳过自己
            if user_id == config.qzone.uin:
                continue

            if user_id not in existing_uins:
                nickname = member.get("nickname", "") or member.get("card", "") or f"群成员{user_id}"
                config.monitor_list.append(MonitorTarget(
                    name=f"{group_name}/{nickname}",
                    uin=user_id,
                    enabled=True,
                ))
                existing_uins.add(user_id)
                added += 1

        logger.info(f"从群 {group_id} 导入 {added} 个新监控目标")
        return added

    def sync_group_sources(self, config: AppConfig) -> int:
        """
        同步所有启用的群来源

        :param config: 应用配置（会被修改）
        :return:       总共新增的监控人数
        """
        total_added = 0
        for gs in config.group_sources:
            if not gs.enabled or not gs.auto_import:
                continue

            members = self.fetch_members(gs.group_id)
            if members is not None:
                added = self.import_to_monitor_list(config, gs.group_id, members)
                total_added += added

        return total_added