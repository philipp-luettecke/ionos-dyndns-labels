#!/bin/bash

log() {
    local log_level=$1  # A string representing the log level provided by the user when calling the function
    local message=$2  # A string representing the message provided by the user when calling the function
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")  # The current date and time at the time the function is called
    # Same layout as watcher.py's own log lines, so the two interleave cleanly.
    echo "$timestamp $log_level $message"
}

if [[ -z "${CRON_SCHEDULE}" ]]; then
    CRON_SCHEDULE="*/15 * * * *"
    log "INFO" "No CRON_SCHEDULE provided. Using default: $CRON_SCHEDULE"
fi

CRON_FILE=/tmp/crontab
echo "$CRON_SCHEDULE python3 /app/watcher.py" > $CRON_FILE

# Validate the cron expression up front
if ! supercronic -test $CRON_FILE; then
    log "ERROR" "Invalid CRON_SCHEDULE: '$CRON_SCHEDULE'"
    exit 1
fi

# Update once right at startup, then continue on the cron schedule
log "INFO" "Reconciling all currently labeled containers"
python3 /app/watcher.py

log "INFO" "Watching Docker events for immediate updates, and re-checking everything on schedule '$CRON_SCHEDULE' (TZ=${TZ:-UTC})"

# Two long-running processes side by side: the event listener reacts the
# moment a labeled container starts, supercronic catches everything else
# (e.g. a public IP change) on CRON_SCHEDULE. If either one dies, stop the
# container so "restart: unless-stopped" brings both back up cleanly.
python3 /app/watcher.py --listen &
LISTEN_PID=$!

supercronic -passthrough-logs -quiet $CRON_FILE &
CRON_PID=$!

trap 'kill -TERM $LISTEN_PID $CRON_PID 2>/dev/null' TERM INT

wait -n $LISTEN_PID $CRON_PID
EXIT_CODE=$?
log "WARN" "One of the background processes exited (code $EXIT_CODE), stopping the container"
kill $LISTEN_PID $CRON_PID 2>/dev/null
exit $EXIT_CODE
