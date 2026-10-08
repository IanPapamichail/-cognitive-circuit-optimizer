from __future__ import annotations

import csv
import json
import platform
import statistics
import time
from pathlib import Path
import importlib

from qiskit import transpile
from qiskit_aer import AerSimulator
from qiskit.quantum_info import hellinger_fidelity

import importlib

cognitive_module = importlib.import_module("2_cognitive_optimizer")
CognitiveOptimizer = cognitive_module.CognitiveOptimizer
TARGET_BASIS = cognitive_module.TARGET_BASIS


# ---------------------------------------------------------
# IBM Fake Eagle
# ---------------------------------------------------------

try:
    from qiskit_ibm_runtime.fake_provider import FakeWashingtonV2 as FakeEagle
except ImportError as exc:
    raise RuntimeError(
        "Το FakeEagleV2 δεν είναι διαθέσιμο. "
        "Έλεγξε την εγκατάσταση του qiskit-ibm-runtime."
    ) from exc


# ---------------------------------------------------------
# Experimental configuration
# ---------------------------------------------------------

N_RUNS = 30
SHOTS = 2000
BASE_SEED = 42

RAW_RESULTS_FILE = Path("statistical_raw_results.csv")
SUMMARY_FILE = Path("statistical_summary.json")


# ---------------------------------------------------------
# Benchmark circuits
# ---------------------------------------------------------

benchmark_module = importlib.import_module(
    "1_generate_benchmarks_and_baselines"
)

create_vqe_ansatz = benchmark_module.create_vqe_ansatz
create_random_circuit = benchmark_module.create_random_circuit


# ---------------------------------------------------------
# Metrics
# ---------------------------------------------------------

def extract_metrics(qc):
    ops = qc.count_ops()

    return {
        "total_gates": sum(ops.values()),
        "depth": qc.depth(),
        "cx_count": ops.get("cx", 0),
    }


def hit_ratio(hits: int, misses: int) -> float:
    total = hits + misses

    if total == 0:
        return 0.0

    return hits / total


# ---------------------------------------------------------
# Seeded Hellinger fidelity
# ---------------------------------------------------------

def evaluate_fidelity_seeded(
    qc,
    seed: int,
    shots: int = SHOTS,
) -> float:

    qc_meas = qc.copy()

    # Ίδια επιλογή με τον υπάρχοντα Cognitive Optimizer
    if qc_meas.parameters:
        parameter_values = {
            parameter: 0.1
            for parameter in qc_meas.parameters
        }

        qc_meas = qc_meas.assign_parameters(parameter_values)

    qc_meas.measure_all()

    ideal_sim = AerSimulator()
    noisy_sim = AerSimulator.from_backend(FakeEagle())

    ideal_transpiled = transpile(
        qc_meas,
        ideal_sim,
        seed_transpiler=seed,
    )

    noisy_transpiled = transpile(
        qc_meas,
        noisy_sim,
        seed_transpiler=seed,
    )

    ideal_counts = ideal_sim.run(
        ideal_transpiled,
        shots=shots,
        seed_simulator=seed,
    ).result().get_counts()

    noisy_counts = noisy_sim.run(
        noisy_transpiled,
        shots=shots,
        seed_simulator=seed,
    ).result().get_counts()

    return float(
        hellinger_fidelity(
            ideal_counts,
            noisy_counts,
        )
    )


# ---------------------------------------------------------
# Cognitive Optimizer experiment
# ---------------------------------------------------------

def run_cognitive(qc, seed: int) -> dict:

    # Νέα, κενή μνήμη σε ΚΑΘΕ repetition
    optimizer = CognitiveOptimizer()

    start = time.perf_counter()

    optimized = optimizer.optimize(qc)

    runtime = time.perf_counter() - start

    metrics = extract_metrics(optimized)

    hits = optimizer.memory.hits
    misses = optimizer.memory.misses

    fidelity = evaluate_fidelity_seeded(
        optimized,
        seed=seed,
    )

    return {
        "method": "Cognitive",
        **metrics,
        "runtime_sec": runtime,
        "memory_hits": hits,
        "memory_misses": misses,
        "hit_ratio": hit_ratio(hits, misses),
        "fidelity": fidelity,
    }


# ---------------------------------------------------------
# Qiskit Level 3 baseline
# ---------------------------------------------------------

def run_qiskit_l3(qc, seed: int) -> dict:

    start = time.perf_counter()

    optimized = transpile(
        qc,
        basis_gates=TARGET_BASIS,
        optimization_level=3,
        seed_transpiler=seed,
    )

    runtime = time.perf_counter() - start

    metrics = extract_metrics(optimized)

    fidelity = evaluate_fidelity_seeded(
        optimized,
        seed=seed,
    )

    return {
        "method": "Qiskit_L3",
        **metrics,
        "runtime_sec": runtime,
        "memory_hits": 0,
        "memory_misses": 0,
        "hit_ratio": 0.0,
        "fidelity": fidelity,
    }


# ---------------------------------------------------------
# Statistics
# ---------------------------------------------------------

METRICS = (
    "total_gates",
    "depth",
    "cx_count",
    "runtime_sec",
    "hit_ratio",
    "fidelity",
)


def summarize(rows: list[dict]) -> dict:

    summary = {}

    for metric in METRICS:
        values = [
            float(row[metric])
            for row in rows
        ]

        summary[metric] = {
            "mean": statistics.mean(values),
            "sd": statistics.stdev(values)
            if len(values) > 1 else 0.0,
            "min": min(values),
            "max": max(values),
        }

    return summary


# ---------------------------------------------------------
# Main experiment
# ---------------------------------------------------------

def main():

    print("=" * 70)
    print("STATISTICAL EVALUATION")
    print("=" * 70)
    print(f"Runs per condition : {N_RUNS}")
    print(f"Shots              : {SHOTS}")
    print(f"Base seed          : {BASE_SEED}")
    print()

    benchmarks = {
        "VQE": create_vqe_ansatz(),
        "Random": create_random_circuit(),
    }

    all_rows = []

    for circuit_name, qc in benchmarks.items():

        print(f"\n--- {circuit_name} ---")

        original_metrics = extract_metrics(qc)

        print(
            f"Original gates={original_metrics['total_gates']}, "
            f"depth={original_metrics['depth']}, "
            f"CX={original_metrics['cx_count']}"
        )

        for run in range(N_RUNS):

            seed = BASE_SEED + run

            print(
                f"[{run + 1:02d}/{N_RUNS}] "
                f"{circuit_name}",
                end="  ",
            )

            cognitive_result = run_cognitive(
                qc,
                seed,
            )

            cognitive_result.update({
                "circuit": circuit_name,
                "run": run + 1,
                "seed": seed,
            })

            all_rows.append(cognitive_result)

            qiskit_result = run_qiskit_l3(
                qc,
                seed,
            )

            qiskit_result.update({
                "circuit": circuit_name,
                "run": run + 1,
                "seed": seed,
            })

            all_rows.append(qiskit_result)

            print(
                f"Cognitive={cognitive_result['runtime_sec']:.6f}s | "
                f"L3={qiskit_result['runtime_sec']:.6f}s"
            )

    # -----------------------------------------------------
    # Raw CSV
    # -----------------------------------------------------

    fieldnames = [
        "circuit",
        "method",
        "run",
        "seed",
        "total_gates",
        "depth",
        "cx_count",
        "runtime_sec",
        "memory_hits",
        "memory_misses",
        "hit_ratio",
        "fidelity",
    ]

    with RAW_RESULTS_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(all_rows)

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    complete_summary = {
        "experiment": {
            "runs": N_RUNS,
            "shots": SHOTS,
            "base_seed": BASE_SEED,
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "results": {},
    }

    for circuit_name in benchmarks:

        complete_summary["results"][circuit_name] = {}

        for method in ("Cognitive", "Qiskit_L3"):

            selected = [
                row
                for row in all_rows
                if row["circuit"] == circuit_name
                and row["method"] == method
            ]

            complete_summary["results"][circuit_name][method] = (
                summarize(selected)
            )

    with SUMMARY_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            complete_summary,
            file,
            indent=4,
        )

    # -----------------------------------------------------
    # Terminal summary
    # -----------------------------------------------------

    print("\n")
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for circuit_name in benchmarks:

        print(f"\n{circuit_name}")

        for method in ("Cognitive", "Qiskit_L3"):

            data = complete_summary[
                "results"
            ][circuit_name][method]

            print(f"\n  {method}")

            for metric in METRICS:

                mean = data[metric]["mean"]
                sd = data[metric]["sd"]

                print(
                    f"    {metric:<14} "
                    f"{mean:.6f} ± {sd:.6f}"
                )

    print(
        f"\nRaw data -> {RAW_RESULTS_FILE}"
    )

    print(
        f"Summary  -> {SUMMARY_FILE}"
    )


if __name__ == "__main__":
    main()
