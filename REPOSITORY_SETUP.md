# 仓库使用说明

本仓库仅包含源码，不包含本机账号、Cookie、数据库和日志。

1. 安装依赖：`pip install -r requirements.txt`。
2. 将 `config.example.yaml` 复制为 `config.yaml`，再在本机配置账号和操作。
3. 运行 `python run.py`。示例默认关闭转发、点赞、评论。

`config.yaml` 和 `data/` 已忽略，请勿强制提交。Web 管理界面仅在可信网络内使用；Flask 会从环境变量 `QQTRANSPOND_SECRET_KEY` 读取会话签名密钥；未设置时每次启动随机生成。多进程部署请设置同一个高强度随机值，并只存于部署环境。
