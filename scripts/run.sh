#!/bin/bash

###### CONFIGURATION ######

BENCHMARKS=(int fp)

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

PARALLAFT_CHECKPOINT_PERIOD=5000000000 # 5b cycles on aarch64, or 5b instructions on x86_64

###########################

set -e
cd "$(dirname "$0")/.."
BASE="$PWD"
export PATH="$BASE/bin:$PATH"

function setup_permissions() {
    echo "Enabling perf counter and ptrace access"
    sudo sysctl -w kernel.yama.ptrace_scope=0 -w kernel.perf_event_paranoid=-1

    echo "Enabling cpufreq access"
    "$BASE/app/parallaft/scripts/fix_cpufreq_permissions.sh"
}

function check_memory() {
    # get free memory
    local free_mem=$(grep MemAvailable /proc/meminfo | awk '{print $2}')

    # check if it's at least 12G
    if [ $free_mem -lt 12582912 ]; then
        local free_mem_gb=$(echo "scale=2; $free_mem / 1024 / 1024" | bc)
        echo "Error: Not enough memory available. You need at least 12GB of available memory. You currently have ${free_mem_gb}GB available."
        exit 1
    fi

    local free_swap=$(grep SwapFree /proc/meminfo | awk '{print $2}')

    # check if the free swap plus free memory is at least 24G
    if [ $((free_mem + free_swap)) -lt 25165824 ]; then
        local free_mem_and_swap_gb=$(echo "scale=2; ($free_mem + $free_swap) / 1024 / 1024" | bc)
        echo "Error: Not enough memory and swap available. You need at least 24GB of available memory and swap combined. You currently have ${free_mem_and_swap_gb}GB. Consider adding swap."
        exit 1
    fi
}

setup_permissions
check_memory

RELEVAL_DIR="$BASE/spec06/releval"
REL_RUN="$RELEVAL_DIR/run.py"

echo "Starting experiment..."
echo "Raw results will be available under $RELEVAL_DIR/run"

for experiment in "${EXPERIMENTS[@]}"; do
    echo "-----------------------------------"
    echo "Starting $experiment run..."
    REL_RUN_EXTRA_ARGS=()
    if [ "$experiment" = "parallaft" -o "$experiment" = "parallaft_dyncpufreq" -o "$experiment" = "parallaft_syscallspec" ]; then
        REL_RUN_EXTRA_ARGS=(
            --parallaft_core_alloc heterogeneous
            --parallaft_checkpoint_period $PARALLAFT_CHECKPOINT_PERIOD
            --no-parallaft_no_log
        )
    fi
    "$REL_RUN" --mode $experiment "${REL_RUN_EXTRA_ARGS[@]}" "${BENCHMARKS[@]}" --overwrite
done
