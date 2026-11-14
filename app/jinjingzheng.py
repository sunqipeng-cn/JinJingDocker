"""进京证自动续签（Docker 定时执行版）

敏感/环境相关配置全部从环境变量读取，改配置只改 .env，不用改代码。

环境变量：
    URL       进京证接口地址，只写 host[:port]，如 jjz.jtgl.beijing.gov.cn:2443
    AUTH      抓包得到的 Authorization 凭证
    SEND_KEY  Server酱微信推送 key（可选，留空则不推送）
    DRY_RUN   1=只检查、不提交；0=需要续签时真正提交（默认 0）

退出码：0=正常（含"无需续签"），1=接口返回错误，2=配置缺失
"""
import os
import sys
from datetime import datetime, timedelta

import requests


def _env(name, default=""):
    return (os.environ.get(name) or default).strip()


# ==================== 配置（来自环境变量） ====================
URL = _env("URL")
AUTH = _env("AUTH")
SEND_KEY = _env("SEND_KEY")
DRY_RUN = _env("DRY_RUN", "0").lower() in ("1", "true", "yes", "on")

# 兼容把地址误填成 https://host:port 的情况
if "://" in URL:
    URL = URL.split("://", 1)[1]
URL = URL.rstrip("/")

if not URL or not AUTH:
    print("[错误] 缺少环境变量 URL 或 AUTH，请检查 .env 配置", file=sys.stderr)
    sys.exit(2)

# 地理信息（按需改动，不懂可以不改。查询经纬度：http://jingweidu.757dy.com/）
SQDZGDJD = "116.328835"  # 社区地址高德经度
SQDZGDWD = "39.725610"   # 社区地址高德纬度
SQDZBDJD = "116.328835"  # 社区地址百度经度
SQDZBDWD = "39.725610"   # 社区地址百度纬度
XXDZ = "北京市大兴区林校路街道永华南里"  # 进京地址

# 接口地址（无需改动）
STATE_LIST_URL = f"https://{URL}/pro/applyRecordController/stateList"          # 查询状态
INSERT_APPLY_RECORD_URL = f"https://{URL}/pro/applyRecordController/insertApplyRecord"  # 办理续签


def request(url, payload=None):
    """调用接口，code != 200 直接退出（cron 日志里能看到原因）"""
    headers = {"Authorization": AUTH, "Content-Type": "application/json"}
    res = requests.post(url, headers=headers, json=payload or {}, timeout=30)
    try:
        data = res.json()
    except ValueError:
        print(f"[错误] 接口返回非 JSON（HTTP {res.status_code}）：{res.text[:300]}", file=sys.stderr)
        sys.exit(1)
    if data.get("code") == 200:
        return data
    print(f"[错误] 请求失败，状态码: {data.get('code')}，错误信息: {data.get('msg')}", file=sys.stderr)
    sys.exit(1)


def pick_record(state_data):
    """取出当前最新的那条证照记录（新证/旧证兜底）"""
    node = state_data["data"]["bzclxx"][0]
    return node["ecbzxx"][0] if node["ecbzxx"] else node["bzxx"][0]


def exec_renew(data, date, jjzzl="六环外"):
    payload = {
        "sqdzgdjd": SQDZGDJD,
        "sqdzgdwd": SQDZGDWD,
        "sqdzbdjd": SQDZBDJD,
        "sqdzbdwd": SQDZBDWD,
        "xxdz": XXDZ,
        "sfzj": "1",              # 是否在京
        "zjxxdz": XXDZ,           # 在京详细地址
        "hpzl": data["hpzl"],     # 车牌类型
        "applyIdOld": data["applyId"],  # 续办申请 id
        "vId": data["vId"],       # 车辆识别代号
        "jsrxm": data["jsrxm"],   # 车主姓名
        "jszh": data["jszh"],     # 车主身份证号
        "hphm": data["hphm"],     # 车牌号
        "txrxx": [],
        "jjdq": "010",            # 进京目的地地区
        "jjmd": "06",             # 进京目的地
        "jjzzl": "01" if jjzzl == "六环内" else "02",  # 进京证类型
        "jjlk": "00606",          # 进京路况
        "jjmdmc": "其它",         # 进京目的地名称
        "jjlkmc": "其他道路",     # 进京路况名称
        "jjrq": date,             # 进京日期（申请生效日期）
    }
    return request(INSERT_APPLY_RECORD_URL, payload)


def send_wechat(title, msg):
    if not SEND_KEY:
        print("[提示] 未配置 SEND_KEY，跳过微信推送")
        return
    try:
        res = requests.get(
            f"https://sctapi.ftqq.com/{SEND_KEY}.send",
            params={"title": title, "desp": msg},
            timeout=15,
        )
        print(f"[server酱] HTTP {res.status_code}: {res.text[:200]}")
    except Exception as exc:  # 推送失败不影响主流程
        print(f"[server酱] 推送失败: {exc}", file=sys.stderr)


def main():
    print(f"===== 进京证检查开始 {datetime.now():%Y-%m-%d %H:%M:%S} =====")
    state_data = request(STATE_LIST_URL)
    data = pick_record(state_data)
    yxqz, blztmc = data["yxqz"], data["blztmc"]
    today = datetime.now().strftime("%Y-%m-%d")

    if blztmc in ["审核通过(生效中)", "审核中", "审核通过(待生效)", "已取消", "失败(审核不通过)"]:
        days_left = (datetime.strptime(yxqz, "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days + 1
        if (blztmc == "审核通过(生效中)" and days_left <= 1) or blztmc in ["已取消", "失败(审核不通过)"]:
            apply_date, flag = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"), True
        else:
            flag = False
    else:
        apply_date, flag = today, True

    if flag:
        if DRY_RUN:
            msg = "需要续签（演练模式，未提交）"
        else:
            exec_renew(data, apply_date)
            msg = "续签成功"
        data = pick_record(request(STATE_LIST_URL))
    else:
        msg = "无需续签"

    yxqs, blztmc, jjzzlmc, sqsj, hphm = (
        data["yxqs"], data["blztmc"], data["jjzzlmc"], data["sqsj"], data["hphm"]
    )
    yxqz = data.get("yxqz") or (
        datetime.strptime(yxqs, "%Y-%m-%d") + timedelta(days=6)
    ).strftime("%Y-%m-%d")
    exec_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"进京证{msg}: {yxqs[5:]}~{yxqz[5:]}"
    content = (
        f"{msg}\n状态: {blztmc}\n有效期: {yxqs}至{yxqz}\n类型: {jjzzlmc}\n"
        f"申请时间: {sqsj}\n执行时间: {exec_time}\n车牌号码: {hphm}"
    )
    print(content)
    send_wechat(title, content)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[错误] 执行异常: {exc}", file=sys.stderr)
        raise
