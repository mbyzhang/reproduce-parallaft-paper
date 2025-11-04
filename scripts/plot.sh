#!/bin/bash

set -e
shopt -s nullglob

cd "$(dirname "$0")/.."
BASE="$PWD"

RUN_DIR="$BASE/spec06/releval/run"
PLOTS_DIR="$BASE/plots"

function find_one_parallaft_result() {
    local dirs=("$RUN_DIR"/parallaft_*_hetero_parallaft-unknown)
    if [ ${#dirs[@]} -ne 1 ]; then
        echo "Expected exactly one parallaft result, but found ${#dirs[@]}:" >&2
        exit 1
    fi
    echo "${dirs[0]}"
}

COLLECT_STATS_ARGS=(
    --base "$RUN_DIR/base"
    --parallaft `find_one_parallaft_result`
    --raft "$RUN_DIR/parallaft_raft_all-big_parallaft-unknown"
    --no-bench-number
    --no-header
    --sep " "
    --scale 100.0
    --geomean
)

if [ `uname -m` = "aarch64" ]; then
    COLLECT_STATS_ARGS+=(
        --base_perf_counters "$RUN_DIR/parallaft_perfcounters_all-big_parallaft-unknown"
    )
fi

function plot_graph() {
    ./tools/collect_stats.py "$1" --output "$PLOTS_DIR/$2.dat" "${COLLECT_STATS_ARGS[@]}" "${@:3}"
    make -C "$PLOTS_DIR" $2.pdf
}

plot_graph performance_overhead_parallaft_vs_raft performance_overhead
plot_graph parallaft_performance_overhead_breakdown performance_overhead_breakdown

if [ `uname -m` = "aarch64" ]; then
    plot_graph energy_overhead_parallaft_vs_raft energy_overhead
fi
