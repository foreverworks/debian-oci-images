#!/bin/sh
# Independent commands side by side. Sourced by the other scripts, never run on its own:
#
#   . "$here/jobs.sh"
#   jobs_begin DIR            DIR is an existing, empty directory that will hold the logs
#   job NAME COMMAND [ARG]... start COMMAND in the background, its output going to DIR/NAME.log
#   jobs_settle               wait for every job, print each log under "== NAME: ok|FAILED" in the
#                             order the jobs started, and return 1 if any of them failed
#
# NAME is a file name without spaces. A job runs in its own process with no standard input, so it
# shares nothing with its siblings but what the caller arranged to be safe to share.

jobs_begin() {
    JOBS_DIR=$1
    : > "$JOBS_DIR/list"
}

job() {
    name=$1
    shift
    "$@" > "$JOBS_DIR/$name.log" 2>&1 < /dev/null &
    echo "$name $!" >> "$JOBS_DIR/list"
}

jobs_settle() {
    failed=0
    while read -r name pid; do
        if wait "$pid"; then
            status=ok
        else
            status=FAILED
            failed=1
        fi
        echo "== $name: $status"
        cat "$JOBS_DIR/$name.log"
    done < "$JOBS_DIR/list"
    : > "$JOBS_DIR/list"
    return "$failed"
}
