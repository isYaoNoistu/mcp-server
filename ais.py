# !/usr/bin/env python3
import os
import sys
import subprocess
import requests
import json
import threading
import getpass

# 环境变量：
# cat >> ~/.bashrc << 'EOF'
# export DEEPSEEK_API_KEY="sk-xxxx"
# export DEEPSEEK_MODEL="deepseek-chat"
# EOF
# source ~/.bashrc

# 使用教程：
# chmod +x ais.py
# sudo ln -s $(pwd)/ais.py /usr/local/bin/ais


DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
API_KEY = os.getenv("DEEPSEEK_API_KEY")

SYSTEM_PROMPT_PATH = os.getenv(
    "DSHELL_SYSTEM_PROMPT",
    os.path.expanduser("./system_prompt.txt")
)

BLOCKED_KEYWORDS = [
    "rm -rf",
    "mkfs",
    "dd ",
    "shutdown",
    "reboot",
]


def load_system_prompt():
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ===== 安全警告：检查是否以root运行 =====
def check_root():
    if os.geteuid() == 0:
        print("\n" + "=" * 50)
        print("⚠️ 警告：检测到以root用户运行AI Shell工具")
        print("⚠️ 重要安全提示：以root身份运行可能带来严重安全风险")
        print("⚠️ 请使用非root用户运行，或使用虚拟环境")
        print("=" * 50 + "\n")
        print("当前用户: " + getpass.getuser())
        print("建议操作: ")
        print("1. 创建普通用户并切换到该用户")
        print("2. 使用虚拟环境: ")
        print("   python3 -m venv venv && source venv/bin/activate")
        print("   pip install -r requirements.txt")
        print("3. 重新运行命令")

        if input("\n是否继续？(y/n) ").lower() != 'y':
            print("操作已取消")
            sys.exit(1)


# ===== DeepSeek 流式调用 =====
def stream_deepseek(messages, prefix=None):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 512,
        "stream": True,
    }

    with requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=payload,
            stream=True,
            timeout=60,
    ) as resp:
        resp.raise_for_status()
        full_text = ""
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if not line.startswith("data:"):
                continue
            data = line.replace("data:", "").strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    if prefix:
                        print(delta, end="", flush=True)
                    full_text += delta
            except Exception:
                continue
        print()
        return full_text.strip()


def is_dangerous(cmd: str) -> bool:
    return any(k in cmd for k in BLOCKED_KEYWORDS)


# ===== 命令流式执行 =====
def stream_execute(cmd: str):
    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    def stream(pipe, label=None):
        for line in pipe:
            print(line, end="", flush=True)

    t_out = threading.Thread(target=stream, args=(process.stdout,))
    t_err = threading.Thread(target=stream, args=(process.stderr,))

    t_out.start()
    t_err.start()

    process.wait()
    t_out.join()
    t_err.join()

    return process.returncode


def main():
    # ===== 安全检查：避免以root运行 =====
    check_root()

    if not API_KEY:
        print("❌ DEEPSEEK_API_KEY 未设置")
        print("请设置环境变量: export DEEPSEEK_API_KEY='your_api_key'")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("用法: ais.py \"自然语言指令\"")
        print("示例: ais.py \"查看系统内存使用情况\"")
        sys.exit(1)

    user_input = " ".join(sys.argv[1:])

    # ===== 1. 流式生成命令 =====
    print("\n▶ 正在生成命令…\n")
    command = stream_deepseek(
        [
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": user_input},
        ],
        prefix=True,
    )

    print("\n▶ 生成完成\n")

    if is_dangerous(command):
        print("❌ 命令包含高危关键词，已阻止执行")
        print("高危关键词: " + ", ".join([k for k in BLOCKED_KEYWORDS if k in command]))
        sys.exit(2)

    # ===== 2. 流式执行命令 =====
    print("▶ 正在执行命令…\n")
    code = stream_execute(command)
    print(f"\n▶ 执行结束，退出码: {code}\n")

    # ===== 3. 流式分析结果 =====
    print("▶ 正在分析执行结果…\n")

    analysis_prompt = f"""
以下是 Linux 命令的真实执行情况，请进行运维分析。

命令：
{command}

退出码：{code}

请输出：
- 关键发现
- 是否异常
- 可能原因
- 运维建议
"""

    stream_deepseek(
        [
            {"role": "system", "content": "你是一个资深 Linux 运维工程师，只分析真实执行结果。"},
            {"role": "user", "content": analysis_prompt},
        ],
        prefix=True,
    )


if __name__ == "__main__":
    main()