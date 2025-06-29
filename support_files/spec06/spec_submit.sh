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
  echo "usage: $0 {strace|sdt|run|parallaft} [PARALLAFT_XARGS...] -- PROGRAM"
}

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

function ensure_small_cores_present() {
  if [ -z "$SMALL_CORES" ]; then
    echo "Error: small cores are not present on your CPU"
    exit 1
  fi
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
  if [ $(uname -m) = "x86_64" ]; then
    local lscpu_result="$(lscpu)"
    local cpu_vendor=$(grep '^Vendor ID:' <<<"$lscpu_result" | awk '{print $NF}')
    local cpu_family=$(grep '^\s*CPU family:' <<<"$lscpu_result" | awk '{print $NF}')
    local cpu_model=$(grep '^\s*Model:' <<<"$lscpu_result" | awk '{print $NF}')

    BIG_CORES_SET_1="2"
    BIG_CORES_SET_2="4,6,8,10"
    SMALL_CORES=""

    if [ "$cpu_vendor" = "GenuineIntel" -a "$cpu_family" = "6" -a "$cpu_model" = "151" ]; then
      # On our Intel i7-12700 machine, CPU 16-19 are small cores
      SMALL_CORES="16,17,18,19"
      PARALLAFT_COMMON_ARGS+=(--max-nr-live-segments 5)
    elif [ "$cpu_vendor" = "GenuineIntel" -a "$cpu_family" = "6" -a "$cpu_model" = "183" ]; then
      # On our Intel i7-14700 machine, CPU 16-27 are small cores
      SMALL_CORES="16,17,18,19,20,21,22,23,24,25,26,27"
      PARALLAFT_COMMON_ARGS+=(--max-nr-live-segments 13)
    else
      PARALLAFT_COMMON_ARGS+=(--max-nr-live-segments 5)
    fi
  else
    BIG_CORES_SET_1="4"
    BIG_CORES_SET_2="5"
    BIG_CORES_SET_ALL="4,5,6,7"
    SMALL_CORES="0,1,2,3"
    PARALLAFT_COMMON_ARGS+=(--max-nr-live-segments 7)
  fi
}

function parallaft_set_cpu_sets() {
  local cpu_vendor=$(lscpu | grep '^Vendor ID:' | awk '{print $NF}')

  local core_alloc="${RELEVAL_PARALLAFT_CORE_ALLOC:-all_big}"

  case "$core_alloc" in
  all-big)
    MAIN_CPU_SET="$BIG_CORES_SET_1"
    CHECKER_CPU_SET="$BIG_CORES_SET_2"
    SHELL_CPU_SET="$BIG_CORES_SET_2"
    ;;
  all-small)
    ensure_small_cores_present
    MAIN_CPU_SET="$SMALL_CORES"
    CHECKER_CPU_SET="$SMALL_CORES"
    SHELL_CPU_SET="$SMALL_CORES"
    ;;
  heterogeneous)
    ensure_small_cores_present
    MAIN_CPU_SET="$BIG_CORES_SET_1"
    CHECKER_CPU_SET="$SMALL_CORES"
    CHECKER_EMERG_CPU_SET="$BIG_CORES_SET_2"
    CHECKER_BOOSTER_CPU_SET="$BIG_CORES_SET_ALL"
    SHELL_CPU_SET="$SMALL_CORES"

    if [ "$cpu_vendor" = "GenuineIntel" ]; then
      PARALLAFT_COMMON_ARGS+=(--enable-intel-hybrid-workaround true)
    fi
    ;;
  inverted-heterogeneous)
    # swap the role of big and small cores
    ensure_small_cores_present
    MAIN_CPU_SET="$SMALL_CORES"
    CHECKER_CPU_SET="$BIG_CORES_SET_2"
    SHELL_CPU_SET="$BIG_CORES_SET_2"

    if [ "$cpu_vendor" = "GenuineIntel" ]; then
      PARALLAFT_COMMON_ARGS+=(--enable-intel-hybrid-workaround true)
    fi
    ;;
  *)
    echo "Error: unsupported \$RELEVAL_PARALLAFT_CORE_ALLOC"
    exit 1
    ;;
  esac

  PARALLAFT_COMMON_ARGS+=(
    --main-cpu-set "$MAIN_CPU_SET"
    --checker-cpu-set "$CHECKER_CPU_SET"
    --shell-cpu-set "$SHELL_CPU_SET"
  )

  if [ -n "$CHECKER_EMERG_CPU_SET" ]; then
    PARALLAFT_COMMON_ARGS+=(--checker-emerg-cpu-set "$CHECKER_EMERG_CPU_SET")
  fi

  if [ -n "$CHECKER_BOOSTER_CPU_SET" ]; then
    PARALLAFT_COMMON_ARGS+=(--checker-booster-cpu-set "$CHECKER_BOOSTER_CPU_SET")
  fi
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
sdt)
  exec soft-dirty-tracer -o "$LOG_PREFIX.mpk" -- "$@"
  ;;
run)
  env >"$LOG_PREFIX.env.txt"

  get_core_config

  /bin/time \
    -f $'timing.main_user_time=%U\ntiming.main_sys_time=%S\ntiming.main_wall_time=%e\ntiming.exit_status=%x\n' \
    -o "$RESULT_PREFIX.stats.txt" \
    taskset -c "$BIG_CORES_SET_1" "$@"
  ;;
parallaft)
  if [ "$RELEVAL_PARALLAFT_NO_LOG" -ne 1 ]; then
    export RUST_LOG=info
  fi

  get_core_config
  parallaft_set_cpu_sets
  parallaft_set_checkpoint_period
  parallaft_enable_perf_counters
  parallaft_enable_core_dump
  parallaft_enable_hwmon

  PARALLAFT_COMMON_ARGS+=(
    --log-output "$LOG_PREFIX.log"
    --stats-output "$RESULT_PREFIX.stats.txt"
  )

  PARALLAFT_EXEC=(
    parallaft
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
