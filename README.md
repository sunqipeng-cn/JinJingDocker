# 进京证自动续签 · Docker 定时任务（飞牛 fnOS）

把 `jinjingzheng.py` 里的 `URL`/`AUTH`/`SEND_KEY` 抽成环境变量，容器内用 cron 定时执行。
纯定时任务：不占端口、不需要持久化数据，结果通过 Server 酱推到微信。

## 目录结构

```
jjz-renewer/
├── app/jinjingzheng.py        # 业务脚本（已改为读环境变量）
├── docker-entrypoint.sh       # 启动时生成 crontab，再前台跑 cron
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env                       # 你的配置（已填好，不要提交到 git）
└── .env.example
```

## 部署到飞牛（3 步）

1. 把整个 `jjz-renewer` 文件夹拷到 NAS 共享文件夹，例如：

```
/vol1/1000/docker/jjz-renewer
```

Windows 上通过 SMB 映射盘直接拖进去即可（`file:///` 方式拷贝会丢隐藏文件 `.env`，注意打开「显示隐藏文件」确认 `.env` 在）。

2. SSH 登录，构建并启动：

```bash
ssh 你的用户名@NAS的IP
sudo -i
cd /vol1/1000/docker/jjz-renewer
docker compose up -d --build
```

3. 看日志确认定时器已就绪：

```bash
docker compose logs -f
```

正常会看到：

```
[entrypoint] 时区      : Asia/Shanghai
[entrypoint] 定时策略  : 0 8 * * *
[entrypoint] 运行模式  : 正式（DRY_RUN=0，需要续签时会真正提交）
[entrypoint] 启动补跑  : 开启（20 秒后执行一次，随后按 cron 定时）
```

> 也可以用 fnOS 图形界面：桌面 **Docker** → 左侧 **compose** → **新建项目** → 存储路径选 `jjz-renewer` 目录 → 使用该目录下已有的 `docker-compose.yml` → 启动。

## 定时策略

`CRON_SCHEDULE` 就是标准 cron 表达式（分 时 日 月 周），容器时区 `Asia/Shanghai`：

| 表达式 | 含义 |
| --- | --- |
| `0 8 * * *` | 每天 08:00（默认） |
| `0 8,20 * * *` | 每天 08:00 和 20:00 |
| `*/30 * * * *` | 每 30 分钟 |
| `0 8 * * 1-5` | 工作日 08:00 |

改完 `.env` 后重启容器生效：

```bash
docker compose up -d --force-recreate
```

另外 `RUN_ON_START=1`（默认）会在每次容器启动 20 秒后补跑一次检查——NAS 半夜断电、早上 8 点没开机，重新开机也能补上，不影响当天续签。想严格只按 cron 执行就设成 `0`。

## 手动测试（不等定时）

```bash
# 演练一次：只查状态、不提交
docker compose run --rm -e DRY_RUN=1 jjz python /app/jinjingzheng.py

# 正式跑一次
docker compose run --rm jjz python /app/jinjingzheng.py
```

## 重要：关于原脚本第 75 行

原脚本里真正提交续签的那行是被注释掉的：

```python
#         exec_renew(data, apply_date)
```

本版本改成了由 `DRY_RUN` 控制，不再靠注释：

- `DRY_RUN=1` → 只检查、消息里写「演练模式，未提交」
- `DRY_RUN=0` → 需要续签时真的调用办理接口

`.env` 里默认已是 `DRY_RUN=0`。**第一次建议先 `DRY_RUN=1` 跑一轮确认接口通、日志正常，再改成 0。**

## 修改进京地址 / 经纬度

脚本里的 `SQDZGDJD`、`SQDZGDWD`、`SQDZBDJD`、`SQDZBDWD`、`XXDZ` 还是硬编码的，改 `app/jinjingzheng.py` 顶部常量后执行：

```bash
docker compose up -d --build
```

## 排错

| 现象 | 原因 / 处理 |
| --- | --- |
| 日志里没有任务输出 | 等过了 cron 时间点；或先手动 `docker compose run --rm ...` 验证 |
| `[错误] 缺少环境变量 URL 或 AUTH` | `.env` 没被拷进去（隐藏文件），或变量名写错 |
| `[错误] 请求失败，状态码: xxx` | AUTH 过期，重新抓包更新 `.env` 后 `docker compose up -d` |
| 容器一直 Restarting | `docker compose logs` 看 entrypoint 报错，多半是 CRON_SCHEDULE 格式不对 |
| 改了 .env 不生效 | 必须 `docker compose up -d --force-recreate`（环境变量在容器创建时注入） |
| 想确认 cron 是否在跑 | `docker compose exec jjz ps aux \| grep cron` |
| 构建时报 `401 Unauthorized` | fnOS 默认配了私有镜像仓库，先手动 `docker pull python:3.12-slim` 成功一次，再 `docker compose up -d --build` |

## 安全提示

`.env` 里有 AUTH 凭证和推送 key，别提交到公开仓库；镜像里不含 `.env`（已写进 `.dockerignore`），容器只在运行时通过 `env_file` 注入。
