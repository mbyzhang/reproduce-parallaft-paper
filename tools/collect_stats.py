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

    Benchmark("2017", "int", "600.perlbench_s", "perlbench_s_base", ["15c0aa", "4be156", "fcb7e9"]),
    Benchmark("2017", "int", "602.gcc_s", "sgcc_base", ["17135e", "7cdedb", "c017f3"]),
    Benchmark("2017", "int", "605.mcf_s", "mcf_s_base", ["eddb77"]),
    Benchmark("2017", "int", "620.omnetpp_s", "omnetpp_s_base", ["af6cf5"]),
    Benchmark("2017", "int", "623.xalancbmk_s", "xalancbmk_s_base", ["5be936"]),
    Benchmark("2017", "int", "625.x264_s", "x264_s_base", ["08617b", "8b6186", "b487f6"]),
    Benchmark("2017", "int", "631.deepsjeng_s", "deepsjeng_s_base", ["5afa1a"]),
    Benchmark("2017", "int", "641.leela_s", "leela_s_base", ["9bc045"]),
    Benchmark("2017", "int", "648.exchange2_s", "exchange2_s_base", ["99e327"]),
    Benchmark("2017", "int", "657.xz_s", "xz_s_base", ["72a258", "d56567"]),

    Benchmark("2017", "fp", "603.bwaves_s", "speed_bwaves_base", ["3e2194", "da7478"]),
    Benchmark("2017", "fp", "607.cactuBSSN_s", "cactuBSSN_s_base", ["2d5bca"]),
    Benchmark("2017", "fp", "619.lbm_s", "lbm_s_base", ["3368e2"]),
    Benchmark("2017", "fp", "621.wrf_s", "wrf_s_base", ["4b795b"]),
    Benchmark("2017", "fp", "627.cam4_s", "cam4_s_base", ["c5ec2f"]),
    Benchmark("2017", "fp", "628.pop2_s", "speed_pop2_base", ["75027c"]),
    Benchmark("2017", "fp", "638.imagick_s", "imagick_s_base", ["f398c7"]),
    Benchmark("2017", "fp", "644.nab_s", "nab_s_base", ["237cf2"]),
    Benchmark("2017", "fp", "649.fotonik3d_s", "fotonik3d_s_base", ["e70412"]),
    Benchmark("2017", "fp", "654.roms_s", "sroms_base", ["a68f1b"]),
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
    (f_main_instructions := Field("perf.main.instructions", int)),
    (f_main_cycles := Field("perf.main.cycles", int)),
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
    f_main_cpu_freq := DerivedField(
        "perf.main.cpu_freq",
        lambda stats: stats[f_main_cycles.name] / (stats[f_main_user_time.name] + stats[f_main_sys_time.name])
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
    PARALLAFT_REF = "parallaft_ref"
    RAFT = "raft"
    CROSS_EXP_DERIVED = "derived"


EXPERIMENT_TYPE_LIST = [
    ExperimentType.BASE,
    ExperimentType.BASE_WITH_PERF_COUNTERS,
    ExperimentType.PARALLAFT,
    ExperimentType.PARALLAFT_REF,
    ExperimentType.RAFT,
]

class Statistic(Enum):
    SINGLE = "single"
    AVERAGE = "average"
    MAX = "max"
    MIN = "min"
    
    def calculate(self, values):
        if self == Statistic.SINGLE:
            assert len(values) == 1, f"Expected a single value, got {len(values)}"
            return values[0]
        elif self == Statistic.AVERAGE:
            return sum(values) / len(values)
        elif self == Statistic.MAX:
            return max(values)
        elif self == Statistic.MIN:
            return min(values)
        else:
            raise ValueError(f"Unknown statistic: {self}")

class CrossExperimentDerivedField(NamedTuple, Generic[T]):
    name: str
    getter: Callable[[Dict[Tuple[ExperimentType, str], Any]], T]


CROSS_EXP_DERIVED_FIELD_LIST = [
    f_parallaft_overhead_perf := CrossExperimentDerivedField(
        "parallaft.overhead.perf",
        lambda stats, stat_ty: (
            stats[(ExperimentType.PARALLAFT, f_all_wall_time.name, stat_ty)]
            - stats[(ExperimentType.BASE, f_main_wall_time.name, Statistic.AVERAGE)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name, Statistic.AVERAGE)],
    ),
    f_parallaft_overhead_perf_runtime_work := CrossExperimentDerivedField(
        "parallaft.overhead.perf.runtime_work",
        lambda stats, stat_ty: (
            stats[(ExperimentType.PARALLAFT, f_main_wall_time.name, stat_ty)]
            - stats[(ExperimentType.PARALLAFT, f_main_cpu_time.name, stat_ty)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name, Statistic.AVERAGE)],
    ),
    f_parallaft_overhead_perf_last_checker_sync := CrossExperimentDerivedField(
        "parallaft.overhead.perf.last_checker_sync",
        lambda stats, stat_ty: (
            stats[(ExperimentType.PARALLAFT, f_all_wall_time.name, stat_ty)]
            - stats[(ExperimentType.PARALLAFT, f_main_wall_time.name, stat_ty)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name, Statistic.AVERAGE)],
    ),
    f_parallaft_overhead_perf_resource_contention := CrossExperimentDerivedField(
        "parallaft.overhead.perf.resource_contention",
        lambda stats, stat_ty: (
            stats[(ExperimentType.PARALLAFT, f_main_user_time.name, stat_ty)]
            - stats[(ExperimentType.BASE, f_main_user_time.name, Statistic.AVERAGE)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name, Statistic.AVERAGE)],
    ),
    f_parallaft_overhead_perf_fork_and_cow := CrossExperimentDerivedField(
        "parallaft.overhead.perf.fork_and_cow",
        lambda stats, stat_ty: (
            stats[(ExperimentType.PARALLAFT, f_main_sys_time.name, stat_ty)]
            - stats[(ExperimentType.BASE, f_main_sys_time.name, Statistic.AVERAGE)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name, Statistic.AVERAGE)],
    ),
    f_parallaft_overhead_energy := CrossExperimentDerivedField(
        "parallaft.overhead.energy",
        lambda stats, stat_ty: (
            stats[(ExperimentType.PARALLAFT, f_hwmon_all_energy.name, stat_ty)]
            - stats[(ExperimentType.BASE_WITH_PERF_COUNTERS, f_hwmon_all_energy.name, Statistic.AVERAGE)]
        )
        / stats[(ExperimentType.BASE_WITH_PERF_COUNTERS, f_hwmon_all_energy.name, Statistic.AVERAGE)],
    ),
    f_raft_overhead_perf := CrossExperimentDerivedField(
        "raft.overhead.perf",
        lambda stats, stat_ty: (
            stats[(ExperimentType.RAFT, f_all_wall_time.name, stat_ty)]
            - stats[(ExperimentType.BASE, f_main_wall_time.name, Statistic.AVERAGE)]
        )
        / stats[(ExperimentType.BASE, f_main_wall_time.name, Statistic.AVERAGE)],
    ),
    f_raft_overhead_energy := CrossExperimentDerivedField(
        "raft.overhead.energy",
        lambda stats, stat_ty: (
            stats[(ExperimentType.RAFT, f_hwmon_all_energy.name, stat_ty)]
            - stats[(ExperimentType.BASE_WITH_PERF_COUNTERS, f_hwmon_all_energy.name, Statistic.AVERAGE)]
        )
        / stats[(ExperimentType.BASE_WITH_PERF_COUNTERS, f_hwmon_all_energy.name, Statistic.AVERAGE)],
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
    exp_stats: OrderedDict[(ExperimentType, str, Union[int, Statistic]), Any],
    stat_ty: Statistic
):
    for f in CROSS_EXP_DERIVED_FIELD_LIST:
        try:
            exp_stats[(ExperimentType.CROSS_EXP_DERIVED, f.name, stat_ty)] = f.getter(exp_stats, stat_ty)
        except KeyError:
            pass


def with_experiment_id_and_type(
    i: int, exp_type: ExperimentType, stats: OrderedDict[str, Any]
) -> OrderedDict[(ExperimentType, str), Any]:
    return OrderedDict([((exp_type, k, i), v) for k, v in stats.items()])


FIELD_GROUPS = {
    "performance_overhead_parallaft_vs_raft": [
        (ExperimentType.CROSS_EXP_DERIVED, f_parallaft_overhead_perf, Statistic.AVERAGE),
        (ExperimentType.CROSS_EXP_DERIVED, f_raft_overhead_perf, Statistic.AVERAGE),
    ],
    "energy_overhead_parallaft_vs_raft": [
        (ExperimentType.CROSS_EXP_DERIVED, f_parallaft_overhead_energy, Statistic.AVERAGE),
        (ExperimentType.CROSS_EXP_DERIVED, f_raft_overhead_energy, Statistic.AVERAGE),
    ],
    "parallaft_performance_overhead_breakdown": [
        (ExperimentType.CROSS_EXP_DERIVED, f_parallaft_overhead_perf_fork_and_cow, Statistic.AVERAGE),
        (
            ExperimentType.CROSS_EXP_DERIVED,
            f_parallaft_overhead_perf_resource_contention,
            Statistic.AVERAGE
        ),
        (ExperimentType.CROSS_EXP_DERIVED, f_parallaft_overhead_perf_last_checker_sync, Statistic.AVERAGE),
        (ExperimentType.CROSS_EXP_DERIVED, f_parallaft_overhead_perf_runtime_work, Statistic.AVERAGE),
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
    parser.add_argument("--spec-ver", default="2006", choices=["2006", "2017"])

    for ty in EXPERIMENT_TYPE_LIST:
        parser.add_argument(f"--{ty.value}", action="append")

    args = parser.parse_args()

    fields = []

    for f in args.fields:
        if f in FIELD_GROUPS:
            fields.extend(FIELD_GROUPS[f])
        elif f in CROSS_EXP_DERIVED_FIELD_LIST_DICT:
            fields.append(
                (ExperimentType.CROSS_EXP_DERIVED, CROSS_EXP_DERIVED_FIELD_LIST_DICT[f], Statistic.AVERAGE)
            )
        else:
            try:
                spec = f.split(":", 3)
                if len(spec) == 2:
                    if spec[0] in CROSS_EXP_DERIVED_FIELD_LIST_DICT:
                        fields.append(
                            (ExperimentType.CROSS_EXP_DERIVED, CROSS_EXP_DERIVED_FIELD_LIST_DICT[spec[0]], Statistic(spec[1]))
                        )
                        continue
                    else:
                        exp_type, field_name = spec
                        stat_ty = Statistic.AVERAGE
                else:
                    exp_type, field_name, stat_ty = spec
            except:
                raise ValueError(
                    f"Invalid field specification: {f}, expecting <exp_type>:<field_name>[:<statistic>] or <derived_field_name>[:<statistic>] or <field_group_name>"
                )

            exp_type = ExperimentType(exp_type)
            if field_name in ALL_FIELD_DICT:
                fields.append((exp_type, ALL_FIELD_DICT[field_name], Statistic(stat_ty)))
            else:
                raise ValueError(f"Unknown field: {field_name}")

    out = []

    experiment_dirs = {}
    for ty in EXPERIMENT_TYPE_LIST:
        dir_names = getattr(args, ty.value)
        if dir_names:
            experiment_dirs[ty] = dir_names

    if len(experiment_dirs) == 0:
        print("No experiment directories are specified", file=sys.stderr)
        sys.exit(1)

    for benchmark in BENCHMARKS:
        if benchmark.suite != args.spec_ver:
            continue

        exp_stats = OrderedDict()

        for exp_type, dir_names in experiment_dirs.items():
            exp_fields = set()
            for i, dir_name in enumerate(dir_names):
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

                exp_fields.update(stats.keys())
                exp_stats.update(with_experiment_id_and_type(i, exp_type, stats))
            
            for s in Statistic.__members__.values():
                for f in exp_fields:
                    try:
                        exp_stats[(exp_type, f, s)] = s.calculate([exp_stats[(exp_type, f, i)] for i in range(len(dir_names))])
                    except:
                        pass
        
        for s in Statistic.__members__.values():
            calculate_cross_exp_derived_fields(exp_stats, s)

        if args.no_bench_number:
            _, benchmark_name = benchmark.name.split(".", 2)
        else:
            benchmark_name = benchmark.name

        out.append(
            [benchmark_name]
            + [exp_stats.get((e, f.name, s), float("nan")) for e, f, s in fields]
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
