#!/usr/bin/python3

from typing import (
    Literal,
    NamedTuple,
    Dict,
    List,
    Callable,
    Any,
    Tuple,
    Type,
    TypeVar,
    Generic,
    Optional,
)
from functools import partial
from socket import gethostname
from typing import TypeVar
from pathlib import Path
from dataclasses_json import dataclass_json
from dataclasses import dataclass
from pprint import pformat

import subprocess
import argparse
from filelock import FileLock, Timeout
import subprocess_tee
import re
import os
import prctl
import signal


class SPECRunResult(NamedTuple):
    result_paths: List[Path]
    stdout: str
    stderr: str


def run_spec(
    benchmarks: List[str],
    runcpu_args: List[str],
    runcpu_env: Dict[str, str],
    exp_name: str,
    spec_dir: Path,
    spec_ver: Literal["2017"] | Literal["2006"] = "2017",
):
    if spec_ver == "2017":
        runcpu_bin = "runcpu"
    elif spec_ver == "2006":
        runcpu_bin = "runspec"
    else:
        raise ValueError("Unsupported SPEC version")

    runcpu_args = (
        [str(spec_dir / "bin" / runcpu_bin), "--config", "releval"]
        + runcpu_args
        + benchmarks
    )

    env = {
        **runcpu_env,
        "SPEC": str(spec_dir.resolve().absolute()),
        "LC_ALL": "C",
        "LC_LANG": "C",
        "SPECPERLLIB": str((spec_dir / "bin/lib").resolve().absolute())
        + ":"
        + str((spec_dir / "bin").resolve().absolute()),
        "RELEVAL_EXP_NAME": exp_name,
        "PATH": str((spec_dir / "bin").resolve().absolute()) + ":" + os.environ["PATH"],
    }

    output = subprocess_tee.run(
        runcpu_args,
        check=True,
        env=env,
        preexec_fn=lambda: prctl.set_pdeathsig(signal.SIGKILL),  # type: ignore
    )

    result_path_matches = re.finditer(
        r"^ *format: raw -> (.+)$", output.stdout, re.MULTILINE
    )

    result_paths = [Path(m.groups()[0]) for m in result_path_matches]

    return SPECRunResult(
        result_paths=result_paths, stdout=output.stdout, stderr=output.stderr
    )


def get_parallaft_ver():
    parallaft_ver = (
        subprocess.check_output(["parallaft", "--version"])
        .decode("utf-8")
        .split(" ", maxsplit=2)[1]
        .strip()
    )

    return parallaft_ver


def get_run_env() -> Dict[str, str]:
    parallaft_ver = get_parallaft_ver()

    if parallaft_ver.endswith("-dirty"):
        raise RuntimeError(
            f"Using dirty parallaft version {parallaft_ver} is forbidden"
        )
    return {
        "parallaft_ver": parallaft_ver,
        "kernel_ver": subprocess.check_output(["uname", "-r"]).decode("utf-8").strip(),
        "hostname": gethostname(),
    }


T = TypeVar("T")
Applier = Callable[[T, List[str], Dict[str, str]], None]


class OptionField(NamedTuple, Generic[T]):
    name: str
    type: Type[T]
    default: T
    choices: Optional[List[T]]
    apply: Applier

    def validate(self, value: Any):
        if not isinstance(value, self.type):
            raise ValueError(
                f"Unexpected type {type(value)} for option {self.name}, expecting {self.type}"
            )

        if self.choices and value not in self.choices:
            raise ValueError(
                f"Unexpected value {value} for option {self.name}, expecting one of {self.choices}"
            )

def get_defs(**kwargs):
    args = []
    for k, v in kwargs.items():
        if isinstance(v, list):
            v = " ".join(v)
        args += ["--define", f"{k}={v}"]
    return args

xargs_fixed_interval_slicing = "--slicer fixed-interval -e true"
xargs_tracker_slicing = "--slicer tracker -e true"
xargs_syscall_speculation = "--syscall-speculation true"
xargs_speculative_reads = "--speculative-reads true"
xargs_double_spec = "--double-speculation true"
xargs_sample_mem_no_rt = "--sample-memory-usage true"
xargs_sample_mem = xargs_sample_mem_no_rt + " --memory-sample-includes-rt true"

RUN_MODES = {
    "base": [],
    "trace_dirty_pages": get_defs(verb="trace-dirty-pages"),
    "sample_ipc": get_defs(verb="sample-ipc"),
    "parallaft": get_defs(verb="parallaft", label_suffix="", parallaft_xargs=xargs_fixed_interval_slicing),
    "parallaft_syscallspec": get_defs(verb="parallaft", label_suffix="", parallaft_xargs=[
        xargs_fixed_interval_slicing,
        xargs_syscall_speculation,
    ]),
    "parallaft_perfcounters": get_defs(verb="parallaft", label_suffix="", parallaft_xargs=xargs_sample_mem_no_rt),
    "parallaft_nofork": get_defs(verb="parallaft", label_suffix="-nofork", parallaft_xargs=["--dont-fork true", xargs_fixed_interval_slicing]),
    "parallaft_nomemcheck": get_defs(verb="parallaft", label_suffix="-nomemcheck", parallaft_xargs=["--no-mem-check true", xargs_fixed_interval_slicing]),
    "parallaft_samplemem": get_defs(verb="parallaft", label_suffix="-samplemem", parallaft_xargs=[xargs_sample_mem, xargs_fixed_interval_slicing]),
    "parallaft_nofork_samplemem": get_defs(verb="parallaft", label_suffix="-nofork-samplemem", parallaft_xargs=["--dont-fork true", xargs_sample_mem, xargs_fixed_interval_slicing]),
    "parallaft_raft": get_defs(verb="parallaft", label_suffix="-raft", parallaft_xargs=[
        "--slicer entire-program",
        "--no-state-cmp true",
        "--dirty-page-tracker none",
        xargs_sample_mem_no_rt,
    ]),
    "parallaft_dynslicing": get_defs(verb="parallaft", label_suffix="-dynslicing", parallaft_xargs="--slicer dynamic -e true"),
    "parallaft_dyncpufreq": get_defs(verb="parallaft", label_suffix="-dyncpufreq", parallaft_xargs=[
        "--cpu-freq-scaler dynamic",
        xargs_fixed_interval_slicing,
        xargs_sample_mem,
    ]),
    "parallaft_dyn2": get_defs(verb="parallaft", label_suffix="-dyn2", parallaft_xargs="--slicer dynamic -e true --cpu-freq-scaler dynamic"),
    "parallaft_tracker_baseline": get_defs(verb="parallaft", label_suffix="-tracker", parallaft_xargs=xargs_tracker_slicing),
    "parallaft_tracker_syscallspec": get_defs(verb="parallaft", label_suffix="-tracker-syscallspec", parallaft_xargs=[
        xargs_tracker_slicing,
        xargs_syscall_speculation,
    ]),
    "parallaft_tracker_specread": get_defs(verb="parallaft", label_suffix="-tracker-specread", parallaft_xargs=[
        xargs_tracker_slicing,
        xargs_syscall_speculation,
        xargs_speculative_reads,
    ]),
    "parallaft_tracker_specread_doublespec": get_defs(verb="parallaft", label_suffix="-tracker-specread-doublespec", parallaft_xargs=[
        xargs_tracker_slicing,
        xargs_syscall_speculation,
        xargs_speculative_reads,
        xargs_double_spec,
    ]),
}

def apply_run_mode(mode: str, runcpu_args: List[str], env: Dict[str, str]):
    try:
        runcpu_args += RUN_MODES[mode]
    except KeyError:
        raise ValueError("Unsupported mode")

def apply_env(env_name: str, env_formatter: Callable[[T], str] = str) -> Applier:
    def inner(
        name: str,
        formatter: Callable[[T], str],
        value: T,
        runcpu_args: List[str],
        env: Dict[str, str],
    ):
        env[name] = formatter(value)

    return partial(inner, env_name, env_formatter)


def bool_to_str(v: bool) -> str:
    return "1" if v else "0"


EXPERIMENT_OPTION_LIST: List[OptionField] = [
    (
        OPT_MODE := OptionField(
            "mode",
            str,
            "base",
            list(RUN_MODES.keys()),
            apply_run_mode,
        )
    ),
    (
        OPT_PARALLAFT_CORE_ALLOC := OptionField(
            "parallaft_core_alloc",
            str,
            "hetero",
            ["all-big", "hetero"],
            apply_env("RELEVAL_PARALLAFT_CORE_ALLOC"),
        )
    ),
    (
        OPT_PARALLAFT_NO_LOG := OptionField(
            "parallaft_no_log",
            bool,
            True,
            None,
            apply_env("RELEVAL_PARALLAFT_NO_LOG", bool_to_str),
        )
    ),
    (
        OPT_PARALLAFT_CHECKPOINT_PERIOD := OptionField(
            "parallaft_checkpoint_period",
            int,
            5_000_000_000,
            None,
            apply_env("RELEVAL_PARALLAFT_CHECKPOINT_PERIOD"),
        )
    ),
    (
        OPT_PARALLAFT_COUNT_CACHE_TLB_EVENTS := OptionField(
            "parallaft_count_cache_tlb_events",
            bool,
            False,
            None,
            apply_env("RELEVAL_PARALLAFT_COUNT_CACHE_TLB_EVENTS", bool_to_str),
        )
    ),
]

has_intel_turbo = False
if Path("/sys/devices/system/cpu/intel_pstate/no_turbo").exists():
    has_intel_turbo = True
    EXPERIMENT_OPTION_LIST += [
        (
            OPT_INTEL_NOTURBO := OptionField(
                "intel_noturbo",
                bool,
                False,
                None,
                apply_env("RELEVAL_INTEL_NOTURBO", bool_to_str),
            )
        )
    ]


EXPERIMENT_OPTION_MAP: Dict[str, OptionField] = {
    option.name: option for option in EXPERIMENT_OPTION_LIST
}


META_FILENAME = "meta.json"
LOCK_FILENAME = "experiment.lock"


@dataclass_json
@dataclass
class Metadata:
    config: Dict[str, Any]
    env: Dict[str, str]

    def __post_init__(self):
        self.cleanup()

    def cleanup(self):
        mode = self.config[OPT_MODE.name]

        if not mode.startswith("parallaft"):
            options_to_delete = [
                OPT_PARALLAFT_CHECKPOINT_PERIOD,
                OPT_PARALLAFT_CORE_ALLOC,
                OPT_PARALLAFT_NO_LOG,
                OPT_PARALLAFT_COUNT_CACHE_TLB_EVENTS,
            ]

            for option in options_to_delete:
                try:
                    del self.config[option.name]
                except:
                    pass

            try:
                del self.env["parallaft_ver"]
            except:
                pass
        elif mode == "parallaft_raft":
            try:
                del self.config[OPT_PARALLAFT_CHECKPOINT_PERIOD.name]
            except:
                pass

    def get_experiment_name(self) -> str:
        mode = self.config[OPT_MODE.name]

        flags = ""
        if has_intel_turbo and self.config[OPT_INTEL_NOTURBO.name]:
            flags += "_noturbo"

        name = f"{mode}{flags}"

        if mode.startswith("parallaft"):
            if mode in (
                "parallaft",
                "parallaft_nofork",
                "parallaft_nomemcheck",
                "parallaft_samplemem",
                "parallaft_nofork_samplemem",
            ):
                name += f"_{self.config[OPT_PARALLAFT_CHECKPOINT_PERIOD.name]}-ipc"

            core_alloc = self.config[OPT_PARALLAFT_CORE_ALLOC.name]
            parallaft_ver = self.env["parallaft_ver"]
            if self.config[OPT_PARALLAFT_NO_LOG.name]:
                flags += "_nolog"

            name += f"_{core_alloc}_parallaft-{parallaft_ver}"

        return name

    def get_spec_cmd_and_env(self) -> Tuple[List[str], Dict[str, str]]:
        spec_args = []
        spec_env = {}

        for name, value in self.config.items():
            option = EXPERIMENT_OPTION_MAP[name]
            option.validate(value)
            option.apply(value, spec_args, spec_env)

        return spec_args, spec_env

    def display(self) -> str:
        def display_dict(d: Dict[str, Any]) -> str:
            return "\n".join(f"- {k}: {v}" for k, v in d.items())

        return f"Config:\n{display_dict(self.config)}\n\nEnvironment:\n{display_dict(self.env)}"


def run_experiment(
    exp_name: str,
    benchmarks: List[str],
    metadata: Metadata,
    releval_dir: Path,
    spec_dir: Path,
    spec_ver: Literal["2017"] | Literal["2006"] = "2017",
    dry_run: bool = False,
    overwrite: bool = False,
):
    print(f"Experiment name: {exp_name}\n\n{metadata.display()}")

    run_dir = releval_dir / "run" / exp_name

    try:
        metadata_ref: Metadata = Metadata.from_json(  # type: ignore
            open(run_dir / META_FILENAME).read()
        )

        if overwrite:
            print(f"Previous metadata:\n{metadata_ref.display()}")
            if metadata != metadata_ref:
                raise RuntimeError(f"Metadata mismatch.")
        else:
            raise RuntimeError("Experiment already exists")

    except FileNotFoundError:
        if not dry_run:
            run_dir.mkdir(parents=True, exist_ok=True)
            open(run_dir / META_FILENAME, "x").write(metadata.to_json())  # type: ignore

    spec_args, spec_env = metadata.get_spec_cmd_and_env()

    if dry_run:
        print(
            f"\nDry run result:\n\nSPEC args:\n{pformat(spec_args)}\n\nSPEC env:\n{pformat(spec_env)}"
        )
        return

    result = run_spec(
        benchmarks,
        spec_args,
        spec_env,
        exp_name,
        spec_dir,
        spec_ver,
    )

    run_result_dir = run_dir / "result"
    run_result_dir.mkdir(parents=True, exist_ok=True)

    for p in result.result_paths:
        (run_result_dir / p.name).symlink_to(p)

    run_log_dir = run_dir / "log"
    (run_log_dir / "spec_stdout.log").write_text(result.stdout)
    (run_log_dir / "spec_stderr.log").write_text(result.stderr)

    print(f"SPEC result written to: {result.result_paths}")


def run_experiment_repeated(
    exp_name: str,
    benchmarks: List[str],
    metadata: Metadata,
    releval_dir: Path,
    spec_dir: Path,
    spec_ver: Literal["2017"] | Literal["2006"] = "2017",
    dry_run: bool = False,
    overwrite: bool = False,
    repeat: int = 1,
):
    for i in range(repeat):
        if repeat != 1:
            name = f"{exp_name}_{i}"
        else:
            name = exp_name

        run_experiment(
            name,
            benchmarks,
            metadata,
            releval_dir,
            spec_dir,
            spec_ver,
            dry_run,
            overwrite,
        )


def main():
    argparser = argparse.ArgumentParser()

    for option in EXPERIMENT_OPTION_LIST:
        if option.type == bool:
            if option.default:
                argparser.add_argument(
                    f"--no-{option.name}", dest=option.name, default=option.default, action="store_false"
                )
            else:
                argparser.add_argument(
                    f"--{option.name}", default=option.default, action="store_true"
                )
        else:
            argparser.add_argument(
                f"--{option.name}",
                type=option.type,
                default=option.default,
                choices=option.choices,
            )

    argparser.add_argument("benchmarks", nargs="+")
    argparser.add_argument("--name", type=str)
    argparser.add_argument(
        "--spec-dir", type=Path, default=Path(__file__).parent.parent
    )
    argparser.add_argument("--releval-dir", type=Path, default=Path(__file__).parent)
    argparser.add_argument("--dry-run", action="store_true")
    argparser.add_argument("--repeat", type=int, default=1)
    argparser.add_argument("--overwrite", action="store_true")
    argparser.add_argument(
        "--spec-ver", choices=["auto", "2017", "2006"], default="auto"
    )
    args = argparser.parse_args()

    if args.spec_ver == "auto":
        spec_ver = "2017" if (args.spec_dir / "benchspec/CPU").exists() else "2006"
        print(f"Auto-detected SPEC version: {spec_ver}")
    else:
        spec_ver = args.spec_ver

    metadata = Metadata(
        {option.name: getattr(args, option.name) for option in EXPERIMENT_OPTION_LIST},
        get_run_env(),
    )

    exp_name = args.name
    if exp_name is None:
        exp_name = metadata.get_experiment_name()

    try:
        with FileLock(args.releval_dir / LOCK_FILENAME, timeout=0):
            run_experiment_repeated(
                exp_name,
                args.benchmarks,
                metadata,
                args.releval_dir,
                args.spec_dir,
                spec_ver,
                args.dry_run,
                args.overwrite,
                args.repeat,
            )
    except Timeout:
        print("Another experiment is running, waiting for it to finish...")
        with FileLock(args.releval_dir / LOCK_FILENAME):
            run_experiment_repeated(
                exp_name,
                args.benchmarks,
                metadata,
                args.releval_dir,
                args.spec_dir,
                spec_ver,
                args.dry_run,
                args.overwrite,
                args.repeat,
            )


if __name__ == "__main__":
    main()
