#!/usr/bin/bash
set -euo pipefail

systemctl is-active --quiet GitToDo.service && echo "Service already active!" && exit 0

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
RUN_PATH=$( dirname "$SCRIPT_DIR" )

echo "Will install GitToDo service definition"
cat "$SCRIPT_DIR/GitToDo.service.template" | \
  sed "s|#SRC_ROOT#|$RUN_PATH|g" | \
  sed "s|#RUN_PATH#|$RUN_PATH|g" | \
  sed "s|#RUN_USER#|$(whoami)|g" | \
  sudo tee >/dev/null /etc/systemd/system/GitToDo.service

echo "Restarting systemctl service"
sudo systemctl daemon-reload
sudo systemctl enable GitToDo
sudo systemctl start GitToDo
sudo systemctl status GitToDo

