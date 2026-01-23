~~~bash
export DEEPSEEK_API_KEY="sk-xxxxxxxx"
export DEEPSEEK_MODEL="deepseek-chat"        # 可选
export DSHELL_SYSTEM_PROMPT="$PWD/system_prompt.txt"

pip install requests

chmod +x dshell.py
sudo ln -s $(pwd)/dshell.py /usr/local/bin/dshell


python dshell.py ""
~~~