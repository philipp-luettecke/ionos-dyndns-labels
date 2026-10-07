#!/bin/bash

log() {
    local log_level=$1  # A string representing the log level provided by the user when calling the function
    local message=$2  # A string representing the message provided by the user when calling the function
    local script_name=$(basename $0)  # The name of the script that is running
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")  # The current date and time at the time the function is called
    echo "$timestamp [$log_level] [$script_name] $message"
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

log "INFO" "Everything seems to be fine now; I will update all labeled containers with schedule '$CRON_SCHEDULE' (TZ=${TZ:-UTC})"

# Update once right at startup, then continue on the cron schedule
log "INFO" "Reconciling all currently labeled containers"
python3 /app/watcher.py

exec supercronic $CRON_FILE
