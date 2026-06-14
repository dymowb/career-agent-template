#!/bin/bash

# Career Agent — daily runner
# Called by cron. Runs discovery then processes queue.

PROJECT_DIR="$HOME/dev/career-agent"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_FILE="$PROJECT_DIR/outputs/career_agent.log"
QUEUE_DIR="$PROJECT_DIR/inputs/queue"
PROCESSED_DIR="$PROJECT_DIR/inputs/processed"

mkdir -p "$QUEUE_DIR"
mkdir -p "$PROCESSED_DIR"
mkdir -p "$PROCESSED_DIR/failed"
mkdir -p "$PROJECT_DIR/outputs"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') — $*" >> "$LOG_FILE"
}

log "starting career agent run"

# 1. Discover new jobs
log "running discovery"
if ! "$VENV_PYTHON" "$PROJECT_DIR/main.py" discover >> "$LOG_FILE" 2>&1; then
    log "discovery failed — continuing with existing queue"
fi

# 2. Process each .txt file independently — failure moves to processed/failed/
#    so it is never retried and never blocks the remaining queue.
count=0
failed=0
for jd_file in "$QUEUE_DIR"/*.txt; do
    [ -f "$jd_file" ] || continue
    filename=$(basename "$jd_file")
    log "processing $filename"
    if "$VENV_PYTHON" "$PROJECT_DIR/main.py" run --jd "$jd_file" >> "$LOG_FILE" 2>&1; then
        mv "$jd_file" "$PROCESSED_DIR/"
        count=$((count + 1))
    else
        log "FAILED $filename (exit $?) — moving to processed/failed/"
        mv "$jd_file" "$PROCESSED_DIR/failed/"
        failed=$((failed + 1))
    fi
done

log "processing done — attempted=$((count + failed)) ok=$count failed=$failed"

# 3. Send digest — digest command exits 0 gracefully when no packs exist
log "running digest"
if ! "$VENV_PYTHON" "$PROJECT_DIR/main.py" digest >> "$LOG_FILE" 2>&1; then
    log "digest command failed"
fi

log "done"
