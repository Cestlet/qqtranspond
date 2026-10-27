"""
QQ空间 API 客户端
通过 HTTP 请求获取指定用户的 QQ 空间动态，以及点赞和评论
"""
import re
import json
import logging
import requests
from typing import List, Optional, Dict, Any
from datetime import datetime
from urllib.parse import quote

logger = logging.getLogger("qqtranspond.qzone")


class QzoneClient:
    """QQ空间客户端，用于获取说说、点赞、评论"""

    def __init__(self, cookies: str, uin: str):
        """
        :param cookies: 浏览器中 qzone.qq.com 域下的完整 Cookie 字符串
        :param uin:     当前登录的 QQ 号
        """
        self.cookies = cookies
        self.uin = uin
        self._g_tk = self._calc_g_tk(cookies)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://user.qzone.qq.com/",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self._set_cookies()

    @staticmethod
    def _calc_g_tk(cookie_str: str) -> int:
        """
        根据 p_skey 或 skey 计算 g_tk (用来调用 qzone api)
        """
        def _get_cookie(key: str) -> str:
            m = re.search(rf'(?:^|;)\s*{re.escape(key)}\s*=\s*([^;]+)', cookie_str)
            return m.group(1) if m else ""

        skey = _get_cookie("p_skey") or _get_cookie("skey") or ""
        h = 5381
        for ch in skey:
            h = h + (h << 5) + ord(ch)
        return h & 0x7fffffff

    def _set_cookies(self):
        """将 Cookie 字符串设置到 session 中"""
        self._session.cookies.clear()
        for item in self.cookies.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                self._session.cookies.set(k.strip(), v.strip(), domain=".qzone.qq.com")

    def _jsonp_parse(self, text: str) -> Optional[dict]:
        """解析 JSONP 回调响应"""
        text = text.strip()
        m = re.match(r'^_preloadCallback\((.*)\);\s*$', text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        # 也可能是纯 JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    # ========== 获取说说 ==========

    def fetch_shuoshuo(
        self,
        target_uin: str,
        num: int = 10,
        pos: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        获取某个 QQ 用户的说说列表

        :param target_uin: 目标 QQ 号
        :param num:        获取条数 (1-35)
        :param pos:        起始偏移
        :return:           说说列表
        """
        url = (
            "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/"
            "cgi-bin/emotion_cgi_msglist_v6"
        )
        params = {
            "uin": target_uin,
            "ftype": 0,
            "sort": 0,
            "pos": pos,
            "num": num,
            "replynum": 0,
            "g_tk": self._g_tk,
            "callback": "_preloadCallback",
            "code_version": 1,
            "format": "jsonp",
            "need_private_comment": 1,
        }
        self._set_cookies()

        try:
            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"请求 Qzone API 失败 ({target_uin}): {e}")
            return []

        data = self._jsonp_parse(resp.text)
        if not data:
            logger.warning(f"Qzone 返回格式异常 (uin={target_uin}): 前100字={resp.text[:100]}")
            return []

        if data.get("code") != 0:
            logger.warning(
                f"Qzone API 返回错误 code={data.get('code')} "
                f"msg={data.get('message', '')} (uin={target_uin})"
            )
            return []

        msglist = data.get("msglist", [])
        results = []
        for msg in msglist:
            content = self._extract_content(msg)
            pics = self._extract_pictures(msg)
            create_time = self._parse_time(msg.get("created_time", 0))

            results.append({
                "tid": msg.get("tid", ""),
                "uin": target_uin,
                "content": content,
                "pictures": pics,
                "create_time": create_time,
                "source_name": msg.get("source_name", ""),
                "certified": msg.get("certified", 0),
            })

        return results

    # ========== 点赞 ==========

    def like_shuoshuo(self, target_uin: str, tid: str) -> bool:
        """
        给一条说说点赞

        :param target_uin: 目标 QQ 号
        :param tid:        说说 ID
        :return:           True 表示成功
        """
        url = (
            "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/"
            "cgi-bin/emotion_cgi_czz_like"
        )
        unikey = f"http://taotao.qq.com/d/{target_uin}_{tid}"

        params = {
            "uin": target_uin,
            "unikey": unikey,
            "tid": tid,
            "fupdate": 1,
            "g_tk": self._g_tk,
            "opr_like": 1,       # 1=点赞, 0=取消
            "format": "json",
        }
        self._set_cookies()

        try:
            resp = self._session.post(url, params=params, timeout=10)
            resp.raise_for_status()
            data = self._jsonp_parse(resp.text) or {}
            if data.get("code") == 0 or data.get("retcode") == 0:
                logger.info(f"点赞成功: uin={target_uin}, tid={tid}")
                return True
            else:
                logger.warning(
                    f"点赞失败: uin={target_uin}, tid={tid}, "
                    f"code={data.get('code')}, msg={data.get('message', '')}"
                )
                return False
        except Exception as e:
            logger.error(f"点赞异常 ({target_uin}, {tid}): {e}")
            return False

    # ========== 评论 ==========

    def comment_shuoshuo(self, target_uin: str, tid: str, content: str) -> bool:
        """
        给一条说说评论

        :param target_uin: 目标 QQ 号
        :param tid:        说说 ID
        :param content:    评论内容（纯文本，建议 10-50 字）
        :return:           True 表示成功
        """
        url = (
            "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/"
            "cgi-bin/emotion_cgi_add_comment"
        )

        # Qzone 评论接口需要 GB2312 编码
        try:
            content_gb = content.encode("gb2312")
        except UnicodeEncodeError:
            # 如果包含 GB2312 无法编码的字符，用 UTF-8 替代
            content_gb = content.encode("utf-8")

        params = {
            "uin": target_uin,
            "tid": tid,
            "content": content,
            "g_tk": self._g_tk,
            "hostUin": target_uin,
            "format": "json",
            "inCharset": "GB2312",
            "outCharset": "GB2312",
            "code_version": 1,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=GB2312",
        }
        self._set_cookies()

        # 手动构建 GB2312 编码的 POST body
        body_parts = []
        for k, v in params.items():
            if isinstance(v, str):
                try:
                    encoded = v.encode("gb2312")
                except UnicodeEncodeError:
                    encoded = v.encode("utf-8")
                body_parts.append(f"{k}={quote(encoded)}")
            else:
                body_parts.append(f"{k}={v}")

        body = "&".join(body_parts)

        try:
            resp = self._session.post(
                url, data=body.encode("gb2312", errors="replace"),
                headers=headers, timeout=10,
            )
            resp.raise_for_status()
            data = self._jsonp_parse(resp.text) or {}
            if data.get("code") == 0 or data.get("retcode") == 0:
                logger.info(f"评论成功: uin={target_uin}, tid={tid}, content={content[:30]}")
                return True
            else:
                logger.warning(
                    f"评论失败: uin={target_uin}, tid={tid}, "
                    f"code={data.get('code')}, msg={data.get('message', '')}"
                )
                return False
        except Exception as e:
            logger.error(f"评论异常 ({target_uin}, {tid}): {e}")
            return False

    # ========== 工具方法 ==========

    @staticmethod
    def _extract_content(msg: Dict) -> str:
        """从消息体中提取纯文本内容"""
        content = msg.get("content", "") or ""
        return content.strip()

    @staticmethod
    def _extract_pictures(msg: Dict) -> List[str]:
        """提取图片 URL 列表"""
        pics = []
        for pic_info in msg.get("pic", []):
            url = pic_info.get("url_path", "")
            if url:
                if not url.startswith("http"):
                    url = "https://" + url.lstrip("//")
                pics.append(url)
        return pics

    @staticmethod
    def _parse_time(timestamp) -> str:
        """将时间戳转为可读字符串"""
        try:
            ts = int(timestamp)
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            return str(timestamp)

    def get_user_info(self, target_uin: str) -> Optional[Dict[str, Any]]:
        """获取用户基本信息（昵称、头像等）"""
        url = (
            "https://user.qzone.qq.com/proxy/domain/base.qzone.qq.com/"
            "cgi-bin/user/cgi_userinfo_get_all"
        )
        params = {
            "uin": target_uin,
            "g_tk": self._g_tk,
            "callback": "_preloadCallback",
            "format": "jsonp",
        }
        self._set_cookies()
        try:
            resp = self._session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = self._jsonp_parse(resp.text)
            if data and data.get("code") == 0:
                info = data.get("data", {})
                return {
                    "uin": target_uin,
                    "nickname": info.get("nickname", ""),
                    "avatar": info.get("avatar", ""),
                }
        except Exception as e:
            logger.warning(f"获取用户信息失败 ({target_uin}): {e}")
        return None