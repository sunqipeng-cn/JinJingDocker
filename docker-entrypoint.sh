#!/bin/sh
# 容器入口：校验配置 -> 生成 crontab -> 前台运行 cron
set -eu

: "${URL:?环境变量 URL 未设置（检查 .env）}"
: "${AUTH:?环境变量 AUTH 未设置（检查 .env）}"

CRON_SCHEDULE="${CRON_SCHEDULE:-0 8 * * *}"
TZ="${TZ:-Asia/Shanghai}"
DRY_RUN="${DRY_RUN:-0}"
SEND_KEY="${SEND_KEY:-}"
export TZ

# 带参数启动时直接执行（用于手动测试，如 docker compose run --rm app python /app/jinjingzheng.py）
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# cron 不会继承容器环境变量，这里落成一个文件，由 cron 任务 source
{
    printf "export TZ='%s'\n" "$TZ"
    printf "export URL='%s'\n" "$URL"
    printf "export AUTH='%s'\n" "$AUTH"
    printf "export SEND_KEY='%s'\n" "$SEND_KEY"
    printf "export DRY_RUN='%s'\n" "$DRY_RUN"
} > /app/env.sh
chmod 0600 /app/env.sh

# 生成 /etc/cron.d 任务：输出重定向到 PID 1 的 stdout，统一进 docker logs
cat > /etc/cron.d/jjz <<EOF
SHELL=/bin/sh
PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin
${CRON_SCHEDULE} root . /app/env.sh && cd /app && exec python /app/jinjingzheng.py >> /proc/1/fd/1 2>&1
EOF
chmod 0644 /etc/cron.d/jjz

echo "[entrypoint] 时区      : ${TZ}"
echo "[entrypoint] 定时策略  : ${CRON_SCHEDULE}"
echo "[entrypoint] 接口地址  : https://${URL}"
echo "[entrypoint] 推送      : $([ -n "$SEND_KEY" ] && echo '已配置 Server酱' || echo '未配置（不推送）')"
if [ "$DRY_RUN" = "1" ]; then
    echo "[entrypoint] 运行模式  : 演练（DRY_RUN=1，只检查不提交）"
else
    echo "[entrypoint] 运行模式  : 正式（DRY_RUN=0，需要续签时会真正提交）"
fi

# 启动后补跑一次：NAS 恰好在定时点断电/重启时，避免错过当天的续签
if [ "${RUN_ON_START:-1}" = "1" ]; then
    echo "[entrypoint] 启动补跑  : 开启（20 秒后执行一次，随后按 cron 定时）"
    (
        sleep 20
        . /app/env.sh
        cd /app && exec python /app/jinjingzheng.py >> /proc/1/fd/1 2>&1
    ) &
else
    echo "[entrypoint] 启动补跑  : 关闭（RUN_ON_START=0）"
fi

# 前台运行，容器停止时 cron 随之退出
exec cron -f
