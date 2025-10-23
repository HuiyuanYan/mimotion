# -*- coding: utf8 -*-
import math
import traceback
from datetime import datetime
import pytz
import uuid

import json
import random
import re
import time
import os

import requests
from util.aes_help import encrypt_data, decrypt_data
import util.zepp_helper as zeppHelper

# 获取默认值转int
def get_int_value_default(_config: dict, _key, default):
    _config.setdefault(_key, default)
    return int(_config.get(_key))


# 获取当前时间对应的最大和最小步数
def get_min_max_by_time(hour=None, minute=None):
    if hour is None:
        hour = time_bj.hour
    if minute is None:
        minute = time_bj.minute
    time_rate = min((hour * 60 + minute) / (22 * 60), 1)
    min_step = get_int_value_default(config, 'MIN_STEP', 18000)
    max_step = get_int_value_default(config, 'MAX_STEP', 25000)
    return int(time_rate * min_step), int(time_rate * max_step)


# 虚拟ip地址
def fake_ip():
    return f"{223}.{random.randint(64, 117)}.{random.randint(0, 255)}.{random.randint(0, 255)}"


# 账号脱敏
def desensitize_user_name(user):
    if len(user) <= 8:
        ln = max(math.floor(len(user) / 3), 1)
        return f'{user[:ln]}***{user[-ln:]}'
    return f'{user[:3]}****{user[-4:]}'


# 获取北京时间
def get_beijing_time():
    target_timezone = pytz.timezone('Asia/Shanghai')
    return datetime.now().astimezone(target_timezone)


# 格式化时间
def format_now():
    return get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")


# 获取时间戳
def get_time():
    current_time = get_beijing_time()
    return "%.0f" % (current_time.timestamp() * 1000)


# pushplus消息推送（通用函数）
def push_plus(token, title, content):
    if not token or token.strip() == '' or token.strip().upper() == 'NO':
        return
    requestUrl = "http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
        "channel": "wechat"
    }
    try:
        response = requests.post(requestUrl, data=data)
        if response.status_code == 200:
            json_res = response.json()
            print(f"pushplus推送完毕：{json_res['code']}-{json_res['msg']}")
        else:
            print("pushplus推送失败")
    except Exception as e:
        print(f"pushplus推送异常: {e}")


class MiMotionRunner:
    def __init__(self, _user, _passwd):
        self.user_id = None
        self.device_id = str(uuid.uuid4())
        user = str(_user)
        password = str(_passwd)
        self.invalid = False
        self.log_str = ""
        if user == '' or password == '':
            self.error = "用户名或密码填写有误！"
            self.invalid = True
            return
        self.password = password
        if (user.startswith("+86")) or "@" in user:
            user = user
        else:
            user = "+86" + user
        self.is_phone = user.startswith("+86")
        self.user = user

    def login(self):
        user_token_info = user_tokens.get(self.user)
        if user_token_info is not None:
            access_token = user_token_info.get("access_token")
            login_token = user_token_info.get("login_token")
            app_token = user_token_info.get("app_token")
            self.device_id = user_token_info.get("device_id", str(uuid.uuid4()))
            self.user_id = user_token_info.get("user_id")
            ok, msg = zeppHelper.check_app_token(app_token)
            if ok:
                self.log_str += "使用加密保存的app_token\n"
                return app_token
            else:
                self.log_str += f"app_token失效 重新获取 last grant time: {user_token_info.get('app_token_time')}\n"
                app_token, msg = zeppHelper.grant_app_token(login_token)
                if app_token is None:
                    self.log_str += f"login_token 失效 重新获取 last grant time: {user_token_info.get('login_token_time')}\n"
                    login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(access_token, self.device_id, self.is_phone)
                    if login_token is None:
                        self.log_str += f"access_token 已失效：{msg} last grant time:{user_token_info.get('access_token_time')}\n"
                        return None
                    else:
                        user_token_info.update({
                            "login_token": login_token,
                            "app_token": app_token,
                            "user_id": user_id,
                            "login_token_time": get_time(),
                            "app_token_time": get_time()
                        })
                        self.user_id = user_id
                        return app_token
                else:
                    self.log_str += "重新获取app_token成功\n"
                    user_token_info["app_token"] = app_token
                    user_token_info["app_token_time"] = get_time()
                    return app_token

        access_token, msg = zeppHelper.login_access_token(self.user, self.password)
        if access_token is None:
            self.log_str += "登录获取accessToken失败：%s" % msg
            return None
        login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(access_token, self.device_id, self.is_phone)
        if login_token is None:
            self.log_str += f"登录提取的 access_token 无效：{msg}"
            return None

        user_token_info = {
            "access_token": access_token,
            "login_token": login_token,
            "app_token": app_token,
            "user_id": user_id,
            "access_token_time": get_time(),
            "login_token_time": get_time(),
            "app_token_time": get_time(),
            "device_id": self.device_id
        }
        user_tokens[self.user] = user_token_info
        return app_token

    def login_and_post_step(self, min_step, max_step):
        if self.invalid:
            return "账号或密码配置有误", False
        app_token = self.login()
        if app_token is None:
            return "登陆失败！", False

        step = str(random.randint(min_step, max_step))
        self.log_str += f"已设置为随机步数范围({min_step}~{max_step}) 随机值:{step}\n"
        ok, msg = zeppHelper.post_fake_brand_data(step, app_token, self.user_id)
        return f"修改步数（{step}）[{msg}]", ok


def push_individual_result(user, token, success, msg):
    if not token or token.strip() in ['', 'NO']:
        return
    status = "成功" if success else "失败"
    content = f'<div>账号：{desensitize_user_name(user)}</div><div>状态：{status}</div><div>详情：{msg}</div>'
    print(f"正在向用户{desensitize_user_name(user)}推送执行结果")
    push_plus(token, f"{format_now()} 刷步数结果", content)
    print(f"向用户{desensitize_user_name(user)}推送执行结果完毕")


def push_global_summary(exec_results, summary):
    if not GLOBAL_PUSH_PLUS_TOKEN or GLOBAL_PUSH_PLUS_TOKEN.strip() in ['', 'NO']:
        return
    if GLOBAL_PUSH_PLUS_HOUR is not None and GLOBAL_PUSH_PLUS_HOUR.isdigit():
        if time_bj.hour != int(GLOBAL_PUSH_PLUS_HOUR):
            print(f"当前设置push_plus推送整点为：{GLOBAL_PUSH_PLUS_HOUR}, 当前整点为：{time_bj.hour}，跳过推送")
            return
    html = f'<div>{summary}</div>'
    if len(exec_results) >= PUSH_PLUS_MAX:
        html += '<div>账号数量过多，详细情况请前往github actions中查看</div>'
    else:
        html += '<ul>'
        for exec_result in exec_results:
            success = exec_result['success']
            if success:
                html += f'<li><span>账号：{desensitize_user_name(exec_result["user"])}</span>刷步数成功，接口返回：{exec_result["msg"]}</li>'
            else:
                html += f'<li><span>账号：{desensitize_user_name(exec_result["user"])}</span>刷步数失败，失败原因：{exec_result["msg"]}</li>'
        html += '</ul>'
    print("正在推送全局执行结果")
    push_plus(GLOBAL_PUSH_PLUS_TOKEN, f"{format_now()} 刷步数通知", html)
    print("全局结果推送完成")


def run_single_account(total, idx, user_mi, passwd_mi, user_push_token=None):
    idx_info = f"[{idx + 1}/{total}]" if idx is not None else ""
    log_str = f"[{format_now()}]\n{idx_info}账号：{desensitize_user_name(user_mi)}\n"
    try:
        runner = MiMotionRunner(user_mi, passwd_mi)
        exec_msg, success = runner.login_and_post_step(min_step, max_step)
        log_str += runner.log_str
        log_str += f'{exec_msg}\n'
        exec_result = {"user": user_mi, "success": success, "msg": exec_msg}
        # 单独推送
        push_individual_result(user_mi, user_push_token, success, exec_msg)
    except Exception as e:
        error_msg = f"执行异常: {str(e)}"
        log_str += error_msg + "\n" + traceback.format_exc()
        exec_result = {"user": user_mi, "success": False, "msg": error_msg}
    print(log_str)
    return exec_result


def execute():
    user_list = users.split('#')
    passwd_list = passwords.split('#')
    token_list = user_push_tokens.split('#') if user_push_tokens else [''] * len(user_list)

    # 对齐长度
    while len(token_list) < len(user_list):
        token_list.append('')

    exec_results = []
    if len(user_list) == len(passwd_list):
        idx, total = 0, len(user_list)
        if use_concurrent:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [
                    executor.submit(run_single_account, total, i, u, p, t)
                    for i, (u, p, t) in enumerate(zip(user_list, passwd_list, token_list))
                ]
                exec_results = [f.result() for f in futures]
        else:
            for user_mi, passwd_mi, token_mi in zip(user_list, passwd_list, token_list):
                exec_results.append(run_single_account(total, idx, user_mi, passwd_mi, token_mi))
                idx += 1
                if idx < total:
                    time.sleep(sleep_seconds)
        if encrypt_support:
            persist_user_tokens()
        success_count = sum(1 for r in exec_results if r['success'])
        summary = f"\n执行账号总数{total}，成功：{success_count}，失败：{total - success_count}"
        print(summary)
        push_global_summary(exec_results, summary)
    else:
        print(f"账号数长度[{len(user_list)}]和密码数长度[{len(passwd_list)}]不匹配，跳过执行")
        exit(1)


def prepare_user_tokens() -> dict:
    data_path = r"encrypted_tokens.data"
    if os.path.exists(data_path):
        with open(data_path, 'rb') as f:
            data = f.read()
        try:
            decrypted_data = decrypt_data(data, aes_key, None)
            return json.loads(decrypted_data.decode('utf-8', errors='strict'))
        except:
            print("密钥不正确或者加密内容损坏 放弃token")
            return dict()
    else:
        return dict()


def persist_user_tokens():
    data_path = r"encrypted_tokens.data"
    origin_str = json.dumps(user_tokens, ensure_ascii=False)
    cipher_data = encrypt_data(origin_str.encode("utf-8"), aes_key, None)
    with open(data_path, 'wb') as f:
        f.write(cipher_data)


if __name__ == "__main__":
    time_bj = get_beijing_time()
    encrypt_support = False
    user_tokens = dict()
    if os.environ.get("AES_KEY"):
        aes_key = os.environ["AES_KEY"].encode('utf-8')
        if len(aes_key) == 16:
            encrypt_support = True
            user_tokens = prepare_user_tokens()
        else:
            print("AES_KEY长度必须为16字节，无法使用加密保存功能")
    if not os.environ.get("CONFIG"):
        print("未配置CONFIG变量，无法执行")
        exit(1)

    config = {}
    try:
        config = json.loads(os.environ["CONFIG"])
    except Exception as e:
        print("CONFIG格式不正确，请检查Secret配置，请严格按照JSON格式：使用双引号包裹字段和值，逗号不能多也不能少")
        traceback.print_exc()
        exit(1)

    # 全局推送 token（汇总）
    GLOBAL_PUSH_PLUS_TOKEN = config.get('GLOBAL_PUSH_PLUS_TOKEN')
    GLOBAL_PUSH_PLUS_HOUR = config.get('PUSH_PLUS_HOUR')  # 兼容原字段名
    PUSH_PLUS_MAX = get_int_value_default(config, 'PUSH_PLUS_MAX', 30)

    # 用户级推送 token（每个用户一个）
    user_push_tokens = config.get('USER_PUSH_PLUS_TOKEN', '')

    sleep_seconds = float(config.get('SLEEP_GAP', 5))
    users = config.get('USER', '')
    passwords = config.get('PWD', '')

    if not users or not passwords:
        print("未正确配置账号密码，无法执行")
        exit(1)

    min_step, max_step = get_min_max_by_time()
    use_concurrent = config.get('USE_CONCURRENT') == 'True'

    if not use_concurrent:
        print(f"多账号执行间隔：{sleep_seconds}秒")

    execute()
