#!/bin/sh
# 新环境一条命令复原：拉记忆 + 恢复凭证 + 打印自检
# 用法：REPO=<你的仓库地址> sh bootstrap.sh
set -e
REPO="${REPO:-https://github.com/<you>/<repo>.git}"
DIR="${DIR:-$HOME/bot-home}"

say(){ echo "[bootstrap] $*"; }

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull -q --ff-only && say "仓库已更新"
else
  git clone -q "$REPO" "$DIR" && say "仓库已克隆到 $DIR"
fi

if [ -f "$DIR/memory/mem.py" ]; then
  python3 "$DIR/memory/mem.py" stats 2>/dev/null || say "记忆库还没初始化（python3 memory/mem.py init）"
fi

say "自检："
python3 -V 2>&1 | sed 's/^/  /'
git -C "$DIR" log -1 --format='  repo head: %h %s'
say "下一步：把 persona.md 贴进你框架的人格配置，然后开工"
