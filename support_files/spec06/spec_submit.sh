#!/bin/bash

# Environment variables
# * RELEVAL_EXP_NAME
# * RELEVAL_PARALLAFT_CORE_ALLOC
# * RELEVAL_PARALLAFT_NO_LOG
# * RELEVAL_PARALLAFT_CHECKPOINT_PERIOD
# * RELEVAL_PARALLAFT_COUNT_CACHE_TLB_EVENTS
# * RELEVAL_INTEL_NOTURBO
# * [todo] RELEVAL_INTEL_L3CA

set -e

if [ -z "$SPEC" ]; then
  echo "Error: Failed to detect SPEC environment"
  exit 1
fi

if [ -z "$RELEVAL_EXP_NAME" ]; then
  echo "Error: \$RELEVAL_EXP_NAME is not set"
  exit 1
fi

ACTION="$1"
shift

function usage {
  echo "usage: $0 {strace|trace-dirty-pages|sample-ipc|run|parallaft} [PARALLAFT_XARGS...] -- PROGRAM"
}

PARALLAFT_BIN=parallaft
PARALLAFT_UTILS_BIN=parallaft-utils

PARALLAFT_XARGS=()
PARALLAFT_COMMON_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
  --)
    shift
    break
    ;;
  *)
    PARALLAFT_XARGS+=("$1")
    shift
    ;;
  esac
done

if [[ -z "$1" ]]; then
  usage
  exit 1
fi

function normalize_cmdline() {
  local exe="$(basename $1)"
  exe="${exe%.*}" # strip SPEC run label
  echo -n "$exe" "${@:2}"
}

function set_intel_noturbo() {
  if [ "$1" -ne 0 -a "$1" -ne 1 ]; then
    echo "Error: invalid Intel noturbo value"
    exit 1
  fi

  local path="/sys/devices/system/cpu/intel_pstate/no_turbo"
  local cur_value=$(cat "$path")
  if [ "$1" -ne "$cur_value" ]; then
    echo "$1" >"$path"
  fi
}

function parallaft_enable_hwmon() {
  local lscpu_result="$(lscpu)"
  local cpu_vendor=$(grep '^Vendor ID:' <<<"$lscpu_result" | awk '{print $NF}')

  if [ $(uname -m) = "aarch64" -a "$cpu_vendor" = "Apple" ]; then
    PARALLAFT_COMMON_ARGS+=(
      --hwmon-sensor-paths "macsmc_hwmon/CPU P-cores Power,macsmc_hwmon/CPU E-cores Power,macsmc_hwmon/SoC Power,macsmc_hwmon/DRAM VDD2H Power,macsmc_hwmon/CPU SRAM 1 Power,macsmc_hwmon/CPU SRAM 2 Power"
    )
  fi
}

function get_core_config() {
  BIG_CPU_SET=`"$PARALLAFT_UTILS_BIN" cpu-tiers | head -n 1 | grep -oP --color=never '(?<=CPUs: )[\\d]+'`
}

function parallaft_set_cpu_alloc() {
  local core_alloc="${RELEVAL_PARALLAFT_CORE_ALLOC:-hetero}"

  PARALLAFT_COMMON_ARGS+=(
    --cpu-alloc "$core_alloc"
  )
}

function parallaft_set_checkpoint_period() {
  local checkpoint_period="${RELEVAL_PARALLAFT_CHECKPOINT_PERIOD:-10000000000}"
  PARALLAFT_COMMON_ARGS+=(--checkpoint-period "$checkpoint_period")
}

function parallaft_enable_perf_counters() {
  if [ $(uname -m) != "x86_64" ]; then
    return
  fi

  local perf_counters="instructions,cycles,energy-cores,energy-pkg"
  if [ -n "$RELEVAL_PARALLAFT_COUNT_CACHE_TLB_EVENTS" -a "$RELEVAL_PARALLAFT_COUNT_CACHE_TLB_EVENTS" = "1" ]; then
    perf_counters="$perf_counters,ll-loads,ll-load-misses,ll-stores,ll-store-misses,dtlb-loads,dtlb-load-misses,dtlb-stores,dtlb-store-misses"
  fi

  PARALLAFT_COMMON_ARGS+=(
    --enabled-perf-counters "$perf_counters"
  )
}

function parallaft_enable_core_dump() {
  local core_dump_dir="${LOG_PREFIX}.cores"
  mkdir -p "$core_dump_dir"
  PARALLAFT_COMMON_ARGS+=(
    --core-dump true
    --core-dump-dir "$core_dump_dir"
  )
}

EXP_DIR="$SPEC/releval/run/$RELEVAL_EXP_NAME"
LOG_DIR="$EXP_DIR/log"
RESULT_DIR="$EXP_DIR/result"

mkdir -p "$EXP_DIR"
mkdir -p "$RESULT_DIR"
mkdir -p "$LOG_DIR"

RUN_ID=`normalize_cmdline "$@"`
STDIN_FILE=`readlink -f /proc/self/fd/0 || true`

# check if stdin exists and does not point to anywhere under /dev
if [[ -n "$STDIN_FILE" && "$STDIN_FILE" != /dev/* ]]; then
  STDIN_FILE=`basename $STDIN_FILE`
  RUN_ID="$RUN_ID < $STDIN_FILE"
fi

RUN_HASH=`echo -n "$RUN_ID" | md5sum | head -c 6`
LOG_PREFIX="$LOG_DIR/$RUN_HASH-$(basename $1)"
RESULT_PREFIX="$RESULT_DIR/$RUN_HASH-$(basename $1)"

echo "$RUN_ID" > "$LOG_PREFIX.run_id.txt"

if [ -n "$RELEVAL_INTEL_NO_TURBO" ]; then
  set_intel_noturbo "$RELEVAL_INTEL_NO_TURBO"
fi

case "$ACTION" in
strace)
  exec time \
    -f $'timing.main_user_time=0\ntiming.main_sys_time=0\ntiming.main_wall_time=%e\ntiming.exit_status=%x\n' \
    -o "$RESULT_PREFIX.stats.txt" \
    strace -f -tt -o "$LOG_PREFIX.strace.log" -- "$@"
  ;;
trace-dirty-pages)
  get_core_config
  exec "$PARALLAFT_UTILS_BIN" trace-dirty-pages -c "$BIG_CPU_SET" -o "$LOG_PREFIX.dp.mpk" -z -s -- "$@"
  ;;
sample-ipc)
  get_core_config
  exec "$PARALLAFT_UTILS_BIN" sample-ipc -c 16 -o "$LOG_PREFIX.ipc.mpk" -- "$@"
  ;;
run)
  env >"$LOG_PREFIX.env.txt"

  get_core_config

  /bin/time \
    -f $'timing.main_user_time=%U\ntiming.main_sys_time=%S\ntiming.main_wall_time=%e\ntiming.exit_status=%x\n' \
    -o "$RESULT_PREFIX.stats.txt" \
    taskset -c "$BIG_CPU_SET" "$@"
  ;;
parallaft)
  if [ "$RELEVAL_PARALLAFT_NO_LOG" -ne 1 ]; then
    export RUST_LOG=info
  fi

  parallaft_set_cpu_alloc
  parallaft_set_checkpoint_period
  parallaft_enable_perf_counters
  parallaft_enable_core_dump
  parallaft_enable_hwmon

  PARALLAFT_COMMON_ARGS+=(
    --log-output "$LOG_PREFIX.log"
    --stats-output "$RESULT_PREFIX.stats.txt"
  )

  PARALLAFT_EXEC=(
    timeout -k 5s -s TERM 40m
    "$PARALLAFT_BIN"
    "${PARALLAFT_COMMON_ARGS[@]}"
    "${PARALLAFT_XARGS[@]}"
    --
    "$@"
  )

  echo "${PARALLAFT_EXEC[@]}" >"$LOG_PREFIX.cmd"
  env >"$LOG_PREFIX.env.txt"

  exec "${PARALLAFT_EXEC[@]}"
  ;;
*)
  usage
  exit 1
  ;;
esac
