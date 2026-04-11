#!/bin/bash

###### CONFIGURATION ######

BENCHMARKS=(gobmk)

if [ $(uname -m) = "aarch64" ]; then
    EXPERIMENTS=(
        base                   # A baseline run without Parallaft
        parallaft_perfcounters # A profiling run to get the baseline energy consumption
        parallaft_dyncpufreq   # A Parallaft run with dynamic frequency scaling enabled
        parallaft_raft         # A RAFT run
    )
else
    EXPERIMENTS=(
        base           # A baseline run without Parallaft
        parallaft      # A Parallaft run
        parallaft_raft # A RAFT run
    )
fi

PARALLAFT_CHECKPOINT_PERIOD=5000000000 # 5b cycles

EXTRA_ARGS=(
    # --repeat 3
)
###########################

SPEC_VER=2006
set -e
source "$(dirname "$0")/run_common.sh"
setup_permissions
check_memory
run_experiments "${EXTRA_ARGS[@]}"
