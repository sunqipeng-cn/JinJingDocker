FROM python:3.12-slim

# 日志实时输出 + 不生成 .pyc + 容器时区
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    DEBIAN_FRONTEND=noninteractive

# cron：容器内定时器；tzdata：保证 TZ=Asia/Shanghai 生效
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖，利用构建缓存（国内用阿里云 PyPI 源）
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
        -i https://mirrors.aliyun.com/pypi/simple/

COPY app/ /app/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

# 入口脚本会在启动时按 CRON_SCHEDULE 生成 crontab，然后前台运行 cron
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
