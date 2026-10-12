#!/bin/zsh
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  echo 'README.md のmacOSセットアップを先に実行してください。'
  read '?Enterで終了'
  exit 1
fi
mkdir -p logs
.venv/bin/python main.py "$@" 2> >(tee logs/startup.log >&2)
result=$?
if (( result != 0 )); then
  echo '起動に失敗しました。logs/startup.log を確認してください。'
  read '?Enterで終了'
fi
exit $result
