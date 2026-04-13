#!/bin/bash

###### CONFIGURATION ######

BENCHMARKS=(intspeed fpspeed)

EXPERIMENTS=(
    base           # A baseline run without Parallaft
    parallaft      # A Parallaft run
    parallaft_raft # A RAFT run
)

PARALLAFT_CHECKPOINT_PERIOD=5000000000 # 5b cycles

EXTRA_ARGS=(
    # --repeat 3
    # --dataset test
)
###########################

SPEC_VER=2017
set -e
# 627.cam4_s requires large stack size
ulimit -s 131072
source "$(dirname "$0")/run_common.sh"
setup_permissions
check_memory
run_experiments "${EXTRA_ARGS[@]}"
