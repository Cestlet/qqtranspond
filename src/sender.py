"""
OneBot HTTP API 消息发送模块
通过 HTTP 协议向运行中的 OneBot 客户端发送消息
"""
import json
import logging
from typing import List, Optional
from urllib.parse import urljoin

import requests

from .config import ForwardTarget

logger = logging.getLogger("qqtranspond.sender")


class OneBotSender:
    """
    OneBot 协议 (HTTP API) 消息发送器
    需要配合 Lagrange / go-cqhttp 等 OneBot 实现使用
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5700, access_token: str = ""):
        """
        :param host:         OneBot HTTP API 地址
        :param port:         OneBot HTTP API 端口
        :param access_token: 访问令牌（可选）
        """
        self.base_url = f"http://{host}:{port}"
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "QQTranspond/1.0",
        })
        if access_token:
            self.session.headers.update({
                "Authorization": f"Bearer {access_token}"
            })

    def send_group_msg(self, group_id: str, message: str) -> bool:
        """发送群消息"""
        url = urljoin(self.base_url, "/send_group_msg")
        payload = {
            "group_id": int(group_id),
            "message": message,
        }
        try:
            resp = self.session.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get("status") == "ok" or data.get("retcode") == 0:
                logger.info(f"群消息发送成功 -> group={group_id}")
                return True
            else:
                logger.warning(f"群消息发送失败: {data} (group={group_id})")
                return False
        except Exception as e:
            logger.error(f"群消息发送异常 ({group_id}): {e}")
            return False

    def send_private_msg(self, user_id: str, message: str) -> bool:
        """发送私聊消息"""
        url = urljoin(self.base_url, "/send_private_msg")
        payload = {
            "user_id": int(user_id),
            "message": message,
        }
        try:
            resp = self.session.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get("status") == "ok" or data.get("retcode") == 0:
                logger.info(f"私聊消息发送成功 -> user={user_id}")
                return True
            else:
                logger.warning(f"私聊消息发送失败: {data} (user={user_id})")
                return False
        except Exception as e:
            logger.error(f"私聊消息发送异常 ({user_id}): {e}")
            return False

    def send_forward(self, target: ForwardTarget, message: str) -> bool:
        """根据转发目标类型发送消息"""
        if not target.enabled:
            return False
        if target.type == "group":
            return self.send_group_msg(target.id, message)
        elif target.type == "private":
            return self.send_private_msg(target.id, message)
        else:
            logger.warning(f"未知的转发目标类型: {target.type}")
            return False

    def send_to_all(self, targets: List[ForwardTarget], message: str) -> int:
        """
        向所有启用的转发目标发送消息
        :return: 成功发送的数量
        """
        success = 0
        for t in targets:
            if self.send_forward(t, message):
                success += 1
        return success

    def get_group_member_list(self, group_id: str) -> Optional[List[dict]]:
        """
        获取群成员列表（可用于批量转发到群成员）
        """
        url = urljoin(self.base_url, "/get_group_member_list")
        payload = {"group_id": int(group_id)}
        try:
            resp = self.session.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get("status") == "ok" or data.get("retcode") == 0:
                return data.get("data", [])
            else:
                logger.warning(f"获取群成员列表失败: {data}")
                return None
        except Exception as e:
            logger.error(f"获取群成员列表异常: {e}")
            return None

    def get_login_info(self) -> Optional[dict]:
        """获取登录信息"""
        url = urljoin(self.base_url, "/get_login_info")
        try:
            resp = self.session.post(url, json={}, timeout=10)
            data = resp.json()
            if data.get("status") == "ok" or data.get("retcode") == 0:
                return data.get("data")
            return None
        except Exception as e:
            logger.error(f"获取登录信息异常: {e}")
            return None

    def check_online(self) -> bool:
        """
        检查 OneBot 服务是否在线（静默探测，失败不写错误日志，
        避免前端状态轮询导致日志刷屏；需要详细错误时请用 get_login_info）
        """
        try:
            resp = self.session.post(
                urljoin(self.base_url, "/get_login_info"),
                json={}, timeout=1.5,
            )
            data = resp.json()
            return bool(data and (data.get("status") == "ok" or data.get("retcode") == 0))
        except Exception:
            return False