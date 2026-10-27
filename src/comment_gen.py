"""
评论生成模块
支持模板随机生成和 AI 调用生成两种模式
"""
import random
import json
import logging
from typing import List, Optional

import requests

from .config import CommentTemplate, AIConfig

logger = logging.getLogger("qqtranspond.comment_gen")


class CommentGenerator:
    """评论生成器"""

    def __init__(
        self,
        templates: List[CommentTemplate],
        ai_config: Optional[AIConfig] = None,
    ):
        """
        :param templates: 评论模板列表
        :param ai_config: AI 配置（可选）
        """
        self.templates = templates
        self.ai_config = ai_config

    # ========== 模板模式 ==========

    def generate_from_template(self, post: dict) -> str:
        """
        从模板列表随机生成评论

        支持的模板变量:
          {nickname}  - 发布者的昵称
          {content}   - 说说的前 20 字
          {time}      - 发布时间

        :param post: 说说数据字典
        :return:     生成的评论内容
        """
        if not self.templates:
            return "说得好！"

        # 按权重随机选择
        weights = [max(t.weight, 1) for t in self.templates]
        template = random.choices(self.templates, weights=weights, k=1)[0]

        # 替换变量
        content = template.content
        nickname = post.get("nickname", "朋友") or "朋友"
        post_content = (post.get("content", "") or "")[:20]
        create_time = post.get("create_time", "")

        content = content.replace("{nickname}", nickname)
        content = content.replace("{content}", post_content)
        content = content.replace("{time}", create_time)

        return content.strip()

    # ========== AI 模式 ==========

    def generate_from_ai(self, post: dict) -> Optional[str]:
        """
        调用 AI API 生成评论

        :param post: 说说数据字典
        :return:     生成的评论内容，失败返回 None
        """
        if not self.ai_config or not self.ai_config.enabled:
            logger.warning("AI 模式未启用")
            return None

        if not self.ai_config.api_key:
            logger.warning("AI API Key 未配置")
            return None

        nickname = post.get("nickname", "朋友") or "朋友"
        post_content = post.get("content", "") or ""
        post_content = post_content[:500]  # 限制长度

        # 构建用户消息
        user_message = (
            f"用户 {nickname} 发布了说说，内容如下：\n"
            f"---\n{post_content}\n---\n"
            f"请生成一条简短、自然的评论（10-30字）。"
        )

        payload = {
            "model": self.ai_config.model,
            "messages": [
                {"role": "system", "content": self.ai_config.system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": self.ai_config.max_tokens,
            "temperature": self.ai_config.temperature,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.ai_config.api_key}",
        }

        try:
            resp = requests.post(
                self.ai_config.api_url,
                json=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            # 兼容 OpenAI 和 DeepSeek 等格式
            choices = data.get("choices", [])
            if choices:
                comment = choices[0].get("message", {}).get("content", "").strip()
                # 清理可能的引号
                comment = comment.strip("\"'「」")
                logger.info(f"AI 生成评论: {comment}")
                return comment
            else:
                logger.warning(f"AI 返回格式异常: {data}")
                return None

        except requests.RequestException as e:
            logger.error(f"AI API 请求失败: {e}")
            return None
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error(f"AI 响应解析失败: {e}")
            return None

    # ========== 统一入口 ==========

    def generate(self, post: dict, mode: str = "template") -> Optional[str]:
        """
        生成评论（统一入口）

        :param post: 说说数据字典
        :param mode: "template" 或 "ai"
        :return:     评论内容，失败返回 None
        """
        if mode == "ai":
            return self.generate_from_ai(post)
        else:
            return self.generate_from_template(post)