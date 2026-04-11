#!/bin/bash

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
    local min_physical_mem_gb=${1:-12.0}
    local min_mem_with_swap_gb=${2:-24.0}

    # get free memory
    local free_mem=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
    local free_mem_gb=$(echo "scale=2; $free_mem / 1024 / 1024" | bc)

    # check if it's at least 12G
    if (( $(echo "$free_mem_gb < $min_physical_mem_gb" | bc -l) )); then
        echo "Error: Not enough memory available. You need at least ${min_physical_mem_gb}GB of available memory. You currently have ${free_mem_gb}GB available."
        exit 1
    fi

    local free_swap=$(grep SwapFree /proc/meminfo | awk '{print $2}')
    local free_mem_and_swap_gb=$(echo "scale=2; ($free_mem + $free_swap) / 1024 / 1024" | bc)

    # check if the free swap plus free memory is at least 24G
    if (( $(echo "$free_mem_and_swap_gb < $min_mem_with_swap_gb" | bc -l) )); then
        echo "Error: Not enough memory and swap available. You need at least ${min_mem_with_swap_gb}GB of available memory and swap combined. You currently have ${free_mem_and_swap_gb}GB. Consider adding swap."
        exit 1
    fi
}

SPEC_VER=${SPEC_VER:-2006}

if [ "$SPEC_VER" = "2006" ]; then
    RELEVAL_DIR="$BASE/spec06/releval"
elif [ "$SPEC_VER" = "2017" ]; then
    RELEVAL_DIR="$BASE/spec17/releval"
else
    echo "Unsupported SPEC version: $SPEC_VER. Supported versions are 2006 and 2017."
    exit 1
fi

REL_RUN="$RELEVAL_DIR/run.py"

function run_experiments() {
    for experiment in "${EXPERIMENTS[@]}"; do
        echo "-----------------------------------"
        echo "Starting $experiment run..."
        REL_RUN_EXTRA_ARGS=()
        if [ "$experiment" = "parallaft" -o "$experiment" = "parallaft_dyncpufreq" -o "$experiment" = "parallaft_syscallspec" ]; then
            REL_RUN_EXTRA_ARGS=(
                --parallaft_checkpoint_period $PARALLAFT_CHECKPOINT_PERIOD
                --no-parallaft_no_log
            )
        fi
        "$REL_RUN" --mode $experiment "${REL_RUN_EXTRA_ARGS[@]}" "${BENCHMARKS[@]}" --overwrite --spec-ver "$SPEC_VER" "$@"
    done
}
