#!/usr/bin/env bash
# Polls the download folder every 30 seconds and renames any new PDFs.

WATCH_DIR="$HOME/Library/CloudStorage/Dropbox/To read/Download"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(which python3)"
fi

LOG="$HOME/Library/Logs/pdf-renamer-watch.log"
mkdir -p "$(dirname "$LOG")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

log "Watching: $WATCH_DIR"
log "Press Ctrl-C to stop."

while true; do
    # Count unformatted PDFs (not yet matching YYMMDD-..-..-..pdf)
    new_pdfs=$(find "$WATCH_DIR" -maxdepth 1 -name "*.pdf" | \
        grep -Ev '/[0-9]{6}-[^/]+-[^/]+-[^/]+\.pdf$' | wc -l | tr -d ' ')

    if [[ "$new_pdfs" -gt 0 ]]; then
        log "Found $new_pdfs unformatted PDF(s) — running rename..."
        "$PYTHON" "$SCRIPT_DIR/rename.py" --yes "$WATCH_DIR" 2>&1 | tee -a "$LOG"
        log "Done."
    fi

    sleep 30
done
