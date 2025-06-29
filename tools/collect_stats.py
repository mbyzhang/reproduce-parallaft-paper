#!/usr/bin/env python3

from enum import Enum
from functools import partial
from typing import (
    Callable,
    Dict,
    Any,
    Generic,
    NamedTuple,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)
from collections import namedtuple, OrderedDict
from copy import deepcopy
from glob import glob
import argparse
import sys
import numpy as np

Benchmark = namedtuple(
    "Benchmark", ["suite", "int_or_fp", "name", "filename", "sub_run_hashes"]
)

BENCHMARKS = [
    Benchmark("2006", "int", "400.perlbench", "perlbench_base", ["306b23", "53063c", "56f39e"]),
    Benchmark("2006", "int", "401.bzip2", "bzip2_base", ["3dfb44", "47607a", "5ff518", "8f5aa6", "c5113e", "cccaf4"]),
    Benchmark("2006", "int", "403.gcc", "gcc_base", ["1bdfa0", "278dd0", "2a05b3", "35e1c1", "3f387c", "9587d2", "adcb6e", "e6e141", "f65744"]),
    Benchmark("2006", "int", "429.mcf", "mcf_base", ["4fb2fd"]),
    Benchmark("2006", "int", "445.gobmk", "gobmk_base", ["2b07a7", "5dc95e", "cdeac7", "def92d", "e4d00b"]),
    Benchmark("2006", "int", "456.hmmer", "hmmer_base", ["ced74f", "df0e1a"]),
    Benchmark("2006", "int", "458.sjeng", "sjeng_base", ["efbd59"]),
    Benchmark("2006", "int", "462.libquantum", "libquantum_base", ["654b4d"]),
    Benchmark("2006", "int", "464.h264ref", "h264ref_base", ["1aafff", "bb8834", "bcba84"]),
    Benchmark("2006", "int", "471.omnetpp", "omnetpp_base", ["ca5180"]),
    Benchmark("2006", "int", "473.astar", "astar_base", ["4a80b8", "ebff19"]),
    Benchmark("2006", "int", "483.xalancbmk", "Xalan_base", ["432258"]),
    Benchmark("2006", "fp", "410.bwaves", "bwaves_base", ["ee089e"]),
    Benchmark("2006", "fp", "416.gamess", "gamess_base", ["1ca871", "6bb65b", "94239b"]),
    Benchmark("2006", "fp", "433.milc", "milc_base", ["508240"]),
    Benchmark("2006", "fp", "434.zeusmp", "zeusmp_base", ["9e6de0"]),
    Benchmark("2006", "fp", "435.gromacs", "gromacs_base", ["a2d10f"]),
    Benchmark("2006", "fp", "436.cactusADM", "cactusADM_base", ["3b331e"]),
    Benchmark("2006", "fp", "437.leslie3d", "leslie3d_base", ["4641ab"]),
    Benchmark("2006", "fp", "444.namd", "namd_base", ["43248b"]),
    Benchmark("2006", "fp", "447.dealII", "dealII_base", ["c2a7d3"]),
    Benchmark("2006", "fp", "450.soplex", "soplex_base", ["a6be97", "c2a843"]),
    Benchmark("2006", "fp", "453.povray", "povray_base", ["9b539e"]),
    Benchmark("2006", "fp", "454.calculix", "calculix_base", ["3722a8"]),
    Benchmark("2006", "fp", "459.GemsFDTD", "GemsFDTD_base", ["29e55c"]),
    Benchmark("2006", "fp", "465.tonto", "tonto_base", ["9507e6"]),
    Benchmark("2006", "fp", "470.lbm", "lbm_base", ["e5f68a"]),
    Benchmark("2006", "fp", "481.wrf", "wrf_base", ["70336d"]),
    Benchmark("2006", "fp", "482.sphinx3", "sphinx_livepretend_base", ["3ab418"]),
]

T = TypeVar("T")
R = TypeVar("R")

FieldAccessor = Callable[["Field[T, R]"], T]


class Field(NamedTuple, Generic[T, R]):
    name: str
    type: Callable[[str], T]
    init: R = 0  # type: ignore
    reducer: Callable[[T, R, FieldAccessor], Union[R, Tuple[T, R]]] = lambda x, y, _: x + y  # type: ignore
    is_ok: Callable[[T], bool] = lambda _: True


max_reducer = lambda x, y, _: max(x, y)


def weighted_sum_reducer(
    weight_field: Field[int, Any]
) -> Callable[
    [float, Tuple[float, int], FieldAccessor], Tuple[float, Tuple[float, int]]
]:
    def reducer(
        weight_field: Field[int, Any],
        x: float,
        y: Tuple[float, int],
        accessor: FieldAccessor,
    ) -> Tuple[float, Tuple[float, int]]:
        prev_sum, prev_weight = y
        curr_weight = accessor(weight_field)
        prev_weight_frac = prev_weight / (prev_weight + curr_weight)
        curr_weight_frac = curr_weight / (prev_weight + curr_weight)
        new_sum = prev_sum * prev_weight_frac + x * curr_weight_frac
        return new_sum, (new_sum, prev_weight + curr_weight)

    return partial(reducer, weight_field)


class DerivedField(NamedTuple, Generic[T]):
    name: str
    getter: Callable[[Dict[str, Any]], T]


FIELD_LIST = [
    (f_main_user_time := Field("timing.main_user_time", float)),
    (f_main_sys_time := Field("timing.main_sys_time", float)),
    (f_checker_user_time := Field("timing.checker_user_time", float)),
    (f_checker_sys_time := Field("timing.checker_sys_time", float)),
    (f_main_wall_time := Field("timing.main_wall_time", float)),
    (f_all_wall_time := Field("timing.all_wall_time", float)),
    (
        f_exit_status := Field(
            "timing.exit_status", int, 0, max_reducer, lambda x: x == 0
        )
    ),
    (f_checkpoint_count := Field("counter.checkpoint_count", int)),
    (f_syscall_count := Field("counter.syscall_count", int)),
    (f_llc_loads := Field("perf.llc_loads", int)),
    (f_llc_load_misses := Field("perf.llc_load_misses", int)),
    (f_llc_stores := Field("perf.llc_stores", int)),
    (f_llc_store_misses := Field("perf.llc_store_misses", int)),
    (f_dtlb_loads := Field("perf.dtlb_loads", int)),
    (f_dtlb_load_misses := Field("perf.dtlb_load_misses", int)),
    (f_dtlb_stores := Field("perf.dtlb_stores", int)),
    (f_dtlb_store_misses := Field("perf.dtlb_store_misses", int)),
    (f_instructions := Field("perf.instructions", int)),
    (f_energy_pkg := Field("perf.energy_pkg", int)),
    (f_energy_cores := Field("perf.energy_cores", int)),
    (f_nr_dirty_pages := Field("dirty_pages.total_dirty_pages", int)),
    (f_memory_num_samples := Field("memory.num_samples", int)),
    (
        f_pss_average := Field(
            "memory.pss_average",
            float,
            (0.0, 0),
            weighted_sum_reducer(f_memory_num_samples),
        )
    ),
    (f_pss_peak := Field("memory.pss_peak", int, 0, max_reducer)),
    (
        f_checkpoint_private_dirty_average := Field(
            "memory.checkpoint_private_dirty_average",
            float,
            (0.0, 0),
            weighted_sum_reducer(f_memory_num_samples),
        )
    ),
    (
        f_checkpoint_private_dirty_peak := Field(
            "memory.checkpoint_private_dirty_peak", int, 0, max_reducer
        )
    ),
    (
        f_working_set_upper_lim_average := Field(
            "memory.working_set_upper_lim_average",
            float,
            (0.0, 0),
            weighted_sum_reducer(f_memory_num_samples),
        )
    ),
    (
        f_working_set_upper_lim_peak := Field(
            "memory.working_set_upper_lim_peak", int, 0, max_reducer
        )
    ),
    (
        f_syscall_entry_handling_time := Field(
            "timing.main_syscall_entry_handling_time", float
        )
    ),
    (f_signal_handling_time := Field("timing.main_signal_handling_time", float)),
    (
        f_syscall_exit_handling_time := Field(
            "timing.main_syscall_exit_handling_time", float
        )
    ),
    (f_checkpointing_time := Field("timing.main_checkpointing_time", float)),
    (f_forking_time := Field("timing.main_checkpointing_forking_time", float)),
    (f_throttling_time := Field("timing.main_throttling_time", float)),
    (f_shell_user_time := Field("timing.shell_user_time", float)),
    (f_shell_sys_time := Field("timing.shell_sys_time", float)),
    (f_hwmon_cpu_p_cores_power := Field("hwmon.macsmc_hwmon/CPU P-cores Power", float)),
    (f_hwmon_cpu_sram_1_power := Field("hwmon.macsmc_hwmon/CPU SRAM 1 Power", float)),
    (f_hwmon_dram_vdd2h_power := Field("hwmon.macsmc_hwmon/DRAM VDD2H Power", float)),
    (f_hwmon_soc_power := Field("hwmon.macsmc_hwmon/SoC Power", float)),
    (f_hwmon_cpu_e_cores_power := Field("hwmon.macsmc_hwmon/CPU E-cores Power", float)),
    (f_hwmon_cpu_sram_2_power := Field("hwmon.macsmc_hwmon/CPU SRAM 2 Power", float)),
    (
        f_hwmon_is_ok := Field(
            "hwmon.is_ok",
            lambda x: x == "true",
            True,
            lambda x, y, _: x and y,
            lambda x: x,
        )
    ),
    (f_sysspec_main_syscall_waiting_time := Field("syscall_speculator.main_syscall_waiting_time", float)),
]

FIELD_DICT = {f.name: f for f in FIELD_LIST}

DERIVED_FIELD_LIST = [
    f_main_cpu_time := DerivedField(
        "timing.main_cpu_time",
        lambda stats: stats[f_main_user_time.name] + stats[f_main_sys_time.name],
    ),
    f_hwmon_all_energy := DerivedField(
        "hwmon.macsmc_hwmon.all_energy",
        lambda stats: sum(
            [
                stats[f.name]
                for f in FIELD_LIST
                if f.name.startswith("hwmon.macsmc_hwmon/")
            ]
        ),
    ),
]


class ExperimentType(Enum):
    BASE = "base"
    BASE_WITH_PERF_COUNTERS = "base_perf_counters"
    PARALLAFT = "parallaft"
    RAFT = "raft"
    CROSS_EXP_DERIVED = "derived"


EXPERIMENT_TYPE_LIST = [
    ExperimentType.BASE,
    ExperimentType.BASE_WITH_PERF_COUNTERS,
    ExperimentType.PARALLAFT,
    ExperimentType.RAFT,
]


class CrossExperimentDerivedField(NamedTuple, Generic[T]):
    name: str
    getter: Callable[[Dict[Tuple[ExperimentType, str], Any]], T]


CROSS_EXP_DERIVED_FIELD_LIST = [
    f_parallaft_overhead_perf := CrossExperimentDerivedField(
        "parallaft.overhead.perf",
        lambda stats: (
            stats[(ExperimentType.PARALLAFT, f_all_wall_time.name)]
            - stats[(ExperimentType.BASE, f_main_wall_time.name)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name)],
    ),
    f_parallaft_overhead_perf_runtime_work := CrossExperimentDerivedField(
        "parallaft.overhead.perf.runtime_work",
        lambda stats: (
            stats[(ExperimentType.PARALLAFT, f_main_wall_time.name)]
            - stats[(ExperimentType.PARALLAFT, f_main_cpu_time.name)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name)],
    ),
    f_parallaft_overhead_perf_last_checker_sync := CrossExperimentDerivedField(
        "parallaft.overhead.perf.last_checker_sync",
        lambda stats: (
            stats[(ExperimentType.PARALLAFT, f_all_wall_time.name)]
            - stats[(ExperimentType.PARALLAFT, f_main_wall_time.name)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name)],
    ),
    f_parallaft_overhead_perf_resource_contention := CrossExperimentDerivedField(
        "parallaft.overhead.perf.resource_contention",
        lambda stats: (
            stats[(ExperimentType.PARALLAFT, f_main_user_time.name)]
            - stats[(ExperimentType.BASE, f_main_user_time.name)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name)],
    ),
    f_parallaft_overhead_perf_fork_and_cow := CrossExperimentDerivedField(
        "parallaft.overhead.perf.fork_and_cow",
        lambda stats: (
            stats[(ExperimentType.PARALLAFT, f_main_sys_time.name)]
            - stats[(ExperimentType.BASE, f_main_sys_time.name)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name)],
    ),
    f_parallaft_overhead_energy := CrossExperimentDerivedField(
        "parallaft.overhead.energy",
        lambda stats: (
            stats[(ExperimentType.PARALLAFT, f_hwmon_all_energy.name)]
            - stats[(ExperimentType.BASE_WITH_PERF_COUNTERS, f_hwmon_all_energy.name)]
        )
        / stats[(ExperimentType.BASE_WITH_PERF_COUNTERS, f_hwmon_all_energy.name)],
    ),
    f_raft_overhead_perf := CrossExperimentDerivedField(
        "raft.overhead.perf",
        lambda stats: (
            stats[(ExperimentType.RAFT, f_all_wall_time.name)]
            - stats[(ExperimentType.BASE, f_main_wall_time.name)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name)],
    ),
    f_raft_overhead_energy := CrossExperimentDerivedField(
        "raft.overhead.energy",
        lambda stats: (
            stats[(ExperimentType.RAFT, f_hwmon_all_energy.name)]
            - stats[(ExperimentType.BASE_WITH_PERF_COUNTERS, f_hwmon_all_energy.name)]
        )
        / stats[(ExperimentType.BASE_WITH_PERF_COUNTERS, f_hwmon_all_energy.name)],
    ),
]

CROSS_EXP_DERIVED_FIELD_LIST_DICT = {f.name: f for f in CROSS_EXP_DERIVED_FIELD_LIST}

ALL_FIELD_DICT = {f.name: f for f in FIELD_LIST + DERIVED_FIELD_LIST}


def parse_stats_file(filename: str) -> Dict[str, Any]:
    out = {}

    with open(filename, "r") as f:
        for line in f.readlines():
            try:
                k, v = line.split("=", 2)
                if k in FIELD_DICT:
                    v = FIELD_DICT[k].type(v)

                out[k] = v
            except:
                pass

    return out


def sum_stats_file(filenames: Sequence[str]) -> OrderedDict[str, Any]:
    stats_sum = OrderedDict()
    reducer_states = {}

    for filename in filenames:
        stats = parse_stats_file(filename)

        for f in FIELD_LIST:
            if f.name in stats:
                r = f.reducer(
                    stats[f.name],
                    reducer_states.get(f.name, deepcopy(f.init)),
                    lambda field: stats[field.name],
                )
                if isinstance(r, tuple):
                    stats_sum[f.name], reducer_states[f.name] = r
                else:
                    stats_sum[f.name] = r
                    reducer_states[f.name] = r

    stats_sum = OrderedDict(
        [(k, v[0] if isinstance(v, tuple) else v) for k, v in stats_sum.items()]
    )

    return stats_sum


def calculate_derived_fields(stats: OrderedDict[str, Any]):
    for f in DERIVED_FIELD_LIST:
        try:
            stats[f.name] = f.getter(stats)
        except KeyError:
            pass


def calculate_cross_exp_derived_fields(
    exp_stats: OrderedDict[(ExperimentType, str), Any]
):
    for f in CROSS_EXP_DERIVED_FIELD_LIST:
        try:
            exp_stats[(ExperimentType.CROSS_EXP_DERIVED, f.name)] = f.getter(exp_stats)
        except KeyError:
            pass


def with_experiment_type(
    exp_type: ExperimentType, stats: OrderedDict[str, Any]
) -> OrderedDict[(ExperimentType, str), Any]:
    return OrderedDict([((exp_type, k), v) for k, v in stats.items()])


FIELD_GROUPS = {
    "performance_overhead_parallaft_vs_raft": [
        (ExperimentType.CROSS_EXP_DERIVED, f_parallaft_overhead_perf),
        (ExperimentType.CROSS_EXP_DERIVED, f_raft_overhead_perf),
    ],
    "energy_overhead_parallaft_vs_raft": [
        (ExperimentType.CROSS_EXP_DERIVED, f_parallaft_overhead_energy),
        (ExperimentType.CROSS_EXP_DERIVED, f_raft_overhead_energy),
    ],
    "parallaft_performance_overhead_breakdown": [
        (ExperimentType.CROSS_EXP_DERIVED, f_parallaft_overhead_perf_fork_and_cow),
        (
            ExperimentType.CROSS_EXP_DERIVED,
            f_parallaft_overhead_perf_resource_contention,
        ),
        (ExperimentType.CROSS_EXP_DERIVED, f_parallaft_overhead_perf_last_checker_sync),
        (ExperimentType.CROSS_EXP_DERIVED, f_parallaft_overhead_perf_runtime_work),
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fields", nargs="+")
    parser.add_argument("--no-header", action="store_true")
    parser.add_argument("--no-names", action="store_true")
    parser.add_argument("--no-bench-number", action="store_true")
    parser.add_argument("--sep", default=",")
    parser.add_argument("--output")
    parser.add_argument("--scale", default=1.0, type=float)
    parser.add_argument("--geomean", action="store_true")

    for ty in EXPERIMENT_TYPE_LIST:
        parser.add_argument(f"--{ty.value}")

    args = parser.parse_args()

    fields = []

    for f in args.fields:
        if f in FIELD_GROUPS:
            fields.extend(FIELD_GROUPS[f])
        elif f in CROSS_EXP_DERIVED_FIELD_LIST_DICT:
            fields.append(
                (ExperimentType.CROSS_EXP_DERIVED, CROSS_EXP_DERIVED_FIELD_LIST_DICT[f])
            )
        else:
            try:
                exp_type, field_name = f.split(":", 2)
            except:
                raise ValueError(
                    f"Invalid field specification: {f}, expecting <exp_type>:<field_name> or <derived_field_name> or <field_group_name>"
                )

            exp_type = ExperimentType(exp_type)
            if field_name in ALL_FIELD_DICT:
                fields.append((exp_type, ALL_FIELD_DICT[field_name]))
            else:
                raise ValueError(f"Unknown field: {field_name}")

    out = []

    experiment_dirs = {}
    for ty in EXPERIMENT_TYPE_LIST:
        dir_name = getattr(args, ty.value)
        if dir_name is not None:
            experiment_dirs[ty] = dir_name

    if len(experiment_dirs) == 0:
        print("No experiment directories are specified", file=sys.stderr)
        sys.exit(1)

    for benchmark in BENCHMARKS:
        exp_stats = OrderedDict()

        for exp_type, dir_name in experiment_dirs.items():
            filenames = [
                glob(
                    f"{dir_name}/result/{sub_run_hash}-{benchmark.filename}.releval*.stats.txt"
                )
                for sub_run_hash in benchmark.sub_run_hashes
            ]

            filenames = [
                filename[0] if len(filename) > 0 else None for filename in filenames
            ]

            if None in filenames:
                stats = OrderedDict()
            else:
                stats = sum_stats_file(filenames)
                calculate_derived_fields(stats)

            exp_stats.update(with_experiment_type(exp_type, stats))

        calculate_cross_exp_derived_fields(exp_stats)

        if args.no_bench_number:
            _, benchmark_name = benchmark.name.split(".", 2)
        else:
            benchmark_name = benchmark.name

        out.append(
            [benchmark_name]
            + [exp_stats.get((e, f.name), float("nan")) for e, f in fields]
        )

    if args.geomean:
        a = np.array(list(zip(*out))[1:], dtype=float) + 1.0
        geomean = a.prod(axis=1) ** (1 / a.shape[1]) - 1.0
        out.append(
            [
                "geomean",
                *geomean,
            ]
        )

    out_buf = ""

    if not args.no_header:
        out_buf += args.sep.join(
            ["name"] + list(map(lambda f: f[0].value + ":" + f[1].name, fields))
        ) + "\n"

    for line in out:
        if args.no_names:
            line = line[1:]

        def stringify_and_scale(x):
            if isinstance(x, float):
                return "{:.4f}".format(x * args.scale)
            return str(x)

        out_buf += args.sep.join(map(stringify_and_scale, line)) + "\n"

    if args.output:
        with open(args.output, "wt") as f:
            f.write(out_buf)
    else:
        print(out_buf, end="")


if __name__ == "__main__":
    main()
