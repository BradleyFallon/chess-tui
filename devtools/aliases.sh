# Chess TUI aliases
unalias chess-tui check-setup update-deps fix-deps install-missing-packages \
  2>/dev/null || true

chess-tui() {
  "${PROJECT_ROOT}/venv/bin/python" -m chess_tui "$@"
}

check-setup() {
  "${PROJECT_ROOT}/venv/bin/python" "${PROJECT_ROOT}/scripts/check-setup.py" "$@"
}

update-deps() {
  "${PROJECT_ROOT}/venv/bin/python" "${PROJECT_ROOT}/scripts/fix-deps.py" "$@"
}

alias fix-deps=update-deps
alias install-missing-packages=update-deps
