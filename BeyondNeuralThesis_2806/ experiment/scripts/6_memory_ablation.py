"""
6_memory_ablation.py

Paired ablation experiment για την επεισοδιακή μνήμη
του CognitiveOptimizer.

Στόχος
------
Να εξεταστεί αν η ενεργή επεισοδιακή μνήμη έχει μετρήσιμη
επίδραση στον χρόνο βελτιστοποίησης σε σχέση με την ίδια
ακριβώς διαδικασία χωρίς memory lookup/store.

Συνθήκες
--------
Memory ON:
    CognitiveOptimizer(use_memory=True)

Memory OFF:
    CognitiveOptimizer(use_memory=False)

Σημαντικό
---------
Το experiment ΔΕΝ μετρά fidelity simulation.
Μετρά αποκλειστικά:

    optimizer.optimize(circuit)

ώστε ο χρόνος να αφορά τον ίδιο τον optimizer.

Για κάθε benchmark:
    - 20 warm-up runs
    - 500 paired measured runs
    - εναλλαγή σειράς ON/OFF
    - αποθήκευση raw δεδομένων σε CSV
    - υπολογισμός mean, SD, median, IQR
    - paired runtime differences

Η δομική ισοδυναμία Memory ON / OFF ελέγχεται
σε κάθε repetition.
"""

import csv
import importlib
import json
import math
import statistics
import time
from pathlib import Path

cog_opt_module = importlib.import_module(
    "2_cognitive_optimizer"
)
CognitiveOptimizer = cog_opt_module.CognitiveOptimizer


# ============================================================
# Experimental configuration
# ============================================================

WARMUP_RUNS = 20
MEASURED_RUNS = 500

RAW_RESULTS_FILE = Path(
    "memory_ablation_raw.csv"
)

SUMMARY_FILE = Path(
    "memory_ablation_summary.json"
)


# ============================================================
# Benchmark import
# ============================================================

benchmark_module = importlib.import_module(
    "1_generate_benchmarks_and_baselines"
)

create_vqe_ansatz = (
    benchmark_module.create_vqe_ansatz
)

create_random_circuit = (
    benchmark_module.create_random_circuit
)


# ============================================================
# Utility functions
# ============================================================

def extract_metrics(qc) -> dict:
    """
    Επιστρέφει τις βασικές δομικές μετρικές
    του κυκλώματος.
    """

    ops = qc.count_ops()

    return {
        "gates": sum(ops.values()),
        "depth": qc.depth(),
        "cx": ops.get("cx", 0),
    }


def percentile(
    values: list[float],
    p: float,
) -> float:
    """
    Υπολογίζει percentile με γραμμική παρεμβολή.

    p πρέπει να βρίσκεται στο [0, 1].
    """

    if not values:
        raise ValueError(
            "Η λίστα τιμών είναι κενή."
        )

    sorted_values = sorted(values)

    if len(sorted_values) == 1:
        return float(sorted_values[0])

    position = (
        len(sorted_values) - 1
    ) * p

    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return float(
            sorted_values[lower_index]
        )

    lower_value = sorted_values[
        lower_index
    ]

    upper_value = sorted_values[
        upper_index
    ]

    fraction = (
        position - lower_index
    )

    return float(
        lower_value
        + (
            upper_value
            - lower_value
        )
        * fraction
    )


def summarize_values(
    values: list[float],
) -> dict:
    """
    Επιστρέφει περιγραφικά στατιστικά.
    """

    if not values:
        return {}

    q1 = percentile(
        values,
        0.25,
    )

    q3 = percentile(
        values,
        0.75,
    )

    return {
        "n": len(values),
        "mean": statistics.mean(
            values
        ),
        "sd": (
            statistics.stdev(values)
            if len(values) > 1
            else 0.0
        ),
        "median": statistics.median(
            values
        ),
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1,
        "min": min(values),
        "max": max(values),
    }


# ============================================================
# Single optimizer execution
# ============================================================

def run_single(
    circuit,
    use_memory: bool,
) -> dict:
    """
    Εκτελεί μία μόνο μέτρηση.

    Ο χρονομετρητής περιλαμβάνει αποκλειστικά
    την optimize().
    """

    optimizer = CognitiveOptimizer(
        use_memory=use_memory
    )

    # --------------------------------------------------------
    # High-resolution timer
    # --------------------------------------------------------

    start_ns = time.perf_counter_ns()

    optimized_qc = optimizer.optimize(
        circuit
    )

    end_ns = time.perf_counter_ns()

    runtime_ns = (
        end_ns - start_ns
    )

    metrics = extract_metrics(
        optimized_qc
    )

    return {
        "runtime_ns": runtime_ns,
        "runtime_ms": runtime_ns / 1_000_000.0,

        "gates": metrics["gates"],
        "depth": metrics["depth"],
        "cx": metrics["cx"],

        "hits": optimizer.memory.hits,
        "misses": optimizer.memory.misses,

        "recalls": optimizer.rule_recalls,
        "discoveries": optimizer.rule_discoveries,

        "direct_resolutions":
            optimizer.direct_resolutions,
    }


# ============================================================
# Warm-up
# ============================================================

def run_warmup(
    benchmark_name: str,
    circuit,
) -> None:
    """
    Εκτελεί warm-up χωρίς να αποθηκεύει αποτελέσματα.

    Η σειρά ON/OFF εναλλάσσεται ώστε να μην ευνοείται
    σταθερά κάποια συνθήκη.
    """

    print(
        f"\nWarm-up: {benchmark_name}"
    )

    for run_index in range(
        WARMUP_RUNS
    ):

        if run_index % 2 == 0:

            run_single(
                circuit,
                True,
            )

            run_single(
                circuit,
                False,
            )

        else:

            run_single(
                circuit,
                False,
            )

            run_single(
                circuit,
                True,
            )

    print(
        f"Warm-up completed "
        f"({WARMUP_RUNS} paired runs)."
    )


# ============================================================
# Structural equivalence check
# ============================================================

def validate_pair(
    benchmark_name: str,
    run_number: int,
    result_on: dict,
    result_off: dict,
) -> None:
    """
    Επιβεβαιώνει ότι Memory ON και Memory OFF
    παράγουν τις ίδιες δομικές μετρικές.

    Αν υπάρξει απόκλιση, το experiment σταματά.
    """

    structural_on = {
        "gates": result_on["gates"],
        "depth": result_on["depth"],
        "cx": result_on["cx"],
    }

    structural_off = {
        "gates": result_off["gates"],
        "depth": result_off["depth"],
        "cx": result_off["cx"],
    }

    if structural_on != structural_off:

        raise RuntimeError(
            "\nStructural mismatch detected!\n"
            f"Benchmark: {benchmark_name}\n"
            f"Run: {run_number}\n"
            f"Memory ON : {structural_on}\n"
            f"Memory OFF: {structural_off}"
        )


# ============================================================
# Main benchmark experiment
# ============================================================

def run_benchmark(
    benchmark_name: str,
    circuit,
) -> list[dict]:
    """
    Εκτελεί το paired memory ablation
    για ένα benchmark.
    """

    print()
    print("=" * 80)
    print(
        f"MEMORY ABLATION — "
        f"{benchmark_name}"
    )
    print("=" * 80)

    # --------------------------------------------------------
    # Warm-up phase
    # --------------------------------------------------------

    run_warmup(
        benchmark_name,
        circuit,
    )

    print(
        f"\nMeasured paired runs: "
        f"{MEASURED_RUNS}"
    )

    rows = []

    # ========================================================
    # Measured paired repetitions
    # ========================================================

    for run_index in range(
        1,
        MEASURED_RUNS + 1,
    ):

        # ----------------------------------------------------
        # Alternate execution order
        # ----------------------------------------------------
        #
        # Odd runs:
        #   ON -> OFF
        #
        # Even runs:
        #   OFF -> ON
        #
        # Αυτό μειώνει systematic order bias.
        # ----------------------------------------------------

        if run_index % 2 == 1:

            order = "ON_OFF"

            result_on = run_single(
                circuit,
                True,
            )

            result_off = run_single(
                circuit,
                False,
            )

        else:

            order = "OFF_ON"

            result_off = run_single(
                circuit,
                False,
            )

            result_on = run_single(
                circuit,
                True,
            )

        # ----------------------------------------------------
        # Regression / equivalence validation
        # ----------------------------------------------------

        validate_pair(
            benchmark_name,
            run_index,
            result_on,
            result_off,
        )

        # ----------------------------------------------------
        # Paired difference
        # ----------------------------------------------------

        delta_ns = (
            result_on["runtime_ns"]
            - result_off["runtime_ns"]
        )

        delta_ms = (
            delta_ns
            / 1_000_000.0
        )

        # ----------------------------------------------------
        # Store Memory ON row
        # ----------------------------------------------------

        rows.append(
            {
                "benchmark":
                    benchmark_name,

                "run":
                    run_index,

                "memory":
                    "ON",

                "order":
                    order,

                "runtime_ns":
                    result_on[
                        "runtime_ns"
                    ],

                "runtime_ms":
                    result_on[
                        "runtime_ms"
                    ],

                "delta_on_minus_off_ns":
                    delta_ns,

                "delta_on_minus_off_ms":
                    delta_ms,

                "gates":
                    result_on["gates"],

                "depth":
                    result_on["depth"],

                "cx":
                    result_on["cx"],

                "hits":
                    result_on["hits"],

                "misses":
                    result_on["misses"],

                "recalls":
                    result_on["recalls"],

                "discoveries":
                    result_on[
                        "discoveries"
                    ],

                "direct_resolutions":
                    result_on[
                        "direct_resolutions"
                    ],
            }
        )

        # ----------------------------------------------------
        # Store Memory OFF row
        # ----------------------------------------------------

        rows.append(
            {
                "benchmark":
                    benchmark_name,

                "run":
                    run_index,

                "memory":
                    "OFF",

                "order":
                    order,

                "runtime_ns":
                    result_off[
                        "runtime_ns"
                    ],

                "runtime_ms":
                    result_off[
                        "runtime_ms"
                    ],

                "delta_on_minus_off_ns":
                    delta_ns,

                "delta_on_minus_off_ms":
                    delta_ms,

                "gates":
                    result_off["gates"],

                "depth":
                    result_off["depth"],

                "cx":
                    result_off["cx"],

                "hits":
                    result_off["hits"],

                "misses":
                    result_off["misses"],

                "recalls":
                    result_off["recalls"],

                "discoveries":
                    result_off[
                        "discoveries"
                    ],

                "direct_resolutions":
                    result_off[
                        "direct_resolutions"
                    ],
            }
        )

        # ----------------------------------------------------
        # Progress indicator
        # ----------------------------------------------------

        if (
            run_index % 50 == 0
            or run_index
            == MEASURED_RUNS
        ):
            print(
                f"Completed "
                f"{run_index}/"
                f"{MEASURED_RUNS}"
            )

    return rows


# ============================================================
# CSV output
# ============================================================

def save_csv(
    rows: list[dict],
) -> None:
    """
    Αποθηκεύει όλα τα raw experimental data.
    """

    if not rows:
        return

    fieldnames = list(
        rows[0].keys()
    )

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
        writer.writerows(rows)


# ============================================================
# Summary generation
# ============================================================

def generate_summary(
    rows: list[dict],
) -> dict:
    """
    Δημιουργεί περιγραφικά στατιστικά
    για κάθε benchmark.
    """

    summary = {
        "configuration": {
            "warmup_runs":
                WARMUP_RUNS,

            "measured_paired_runs":
                MEASURED_RUNS,

            "timer":
                "time.perf_counter_ns",

            "timed_region":
                "CognitiveOptimizer.optimize only",
        },

        "benchmarks": {},
    }

    benchmarks = sorted(
        {
            row["benchmark"]
            for row in rows
        }
    )

    for benchmark in benchmarks:

        benchmark_rows = [
            row
            for row in rows
            if row["benchmark"]
            == benchmark
        ]

        on_rows = [
            row
            for row in benchmark_rows
            if row["memory"] == "ON"
        ]

        off_rows = [
            row
            for row in benchmark_rows
            if row["memory"] == "OFF"
        ]

        on_times = [
            float(row["runtime_ms"])
            for row in on_rows
        ]

        off_times = [
            float(row["runtime_ms"])
            for row in off_rows
        ]

        # Μία paired difference ανά repetition.
        deltas = [
            float(
                row[
                    "delta_on_minus_off_ms"
                ]
            )
            for row in on_rows
        ]

        on_summary = summarize_values(
            on_times
        )

        off_summary = summarize_values(
            off_times
        )

        delta_summary = summarize_values(
            deltas
        )

        # ----------------------------------------------------
        # Descriptive speed ratio
        # ----------------------------------------------------

        median_on = (
            on_summary["median"]
        )

        median_off = (
            off_summary["median"]
        )

        if median_on > 0:
            median_speed_ratio = (
                median_off
                / median_on
            )
        else:
            median_speed_ratio = None

        # ----------------------------------------------------
        # Percentage median difference
        # ----------------------------------------------------

        if median_off > 0:
            median_change_pct = (
                (
                    median_on
                    - median_off
                )
                / median_off
            ) * 100.0
        else:
            median_change_pct = None

        # ----------------------------------------------------
        # Structural metrics
        # ----------------------------------------------------

        first_on = on_rows[0]

        # ----------------------------------------------------
        # Memory statistics
        # ----------------------------------------------------

        recalls = [
            row["recalls"]
            for row in on_rows
        ]

        discoveries = [
            row["discoveries"]
            for row in on_rows
        ]

        hits = [
            row["hits"]
            for row in on_rows
        ]

        misses = [
            row["misses"]
            for row in on_rows
        ]

        summary[
            "benchmarks"
        ][benchmark] = {

            "structure": {
                "gates":
                    first_on["gates"],

                "depth":
                    first_on["depth"],

                "cx":
                    first_on["cx"],
            },

            "memory_on_runtime_ms":
                on_summary,

            "memory_off_runtime_ms":
                off_summary,

            "paired_delta_on_minus_off_ms":
                delta_summary,

            "median_speed_ratio_off_over_on":
                median_speed_ratio,

            "median_runtime_change_pct":
                median_change_pct,

            "memory_statistics": {
                "recalls_unique_values":
                    sorted(set(recalls)),

                "discoveries_unique_values":
                    sorted(
                        set(discoveries)
                    ),

                "hits_unique_values":
                    sorted(set(hits)),

                "misses_unique_values":
                    sorted(set(misses)),
            },
        }

    return summary


# ============================================================
# Human-readable console summary
# ============================================================

def print_summary(
    summary: dict,
) -> None:
    """
    Εμφανίζει τα βασικά αποτελέσματα
    στο terminal.
    """

    print()
    print("=" * 80)
    print("FINAL MEMORY ABLATION SUMMARY")
    print("=" * 80)

    for benchmark, data in (
        summary["benchmarks"].items()
    ):

        print()
        print(
            f"{benchmark}"
        )

        print("-" * 80)

        structure = data[
            "structure"
        ]

        print(
            "Structure"
        )

        print(
            f"  Gates : "
            f"{structure['gates']}"
        )

        print(
            f"  Depth : "
            f"{structure['depth']}"
        )

        print(
            f"  CX    : "
            f"{structure['cx']}"
        )

        on_stats = data[
            "memory_on_runtime_ms"
        ]

        off_stats = data[
            "memory_off_runtime_ms"
        ]

        delta_stats = data[
            "paired_delta_on_minus_off_ms"
        ]

        print()
        print(
            "Memory ON runtime"
        )

        print(
            f"  Mean   : "
            f"{on_stats['mean']:.6f} ms"
        )

        print(
            f"  SD     : "
            f"{on_stats['sd']:.6f} ms"
        )

        print(
            f"  Median : "
            f"{on_stats['median']:.6f} ms"
        )

        print(
            f"  IQR    : "
            f"{on_stats['iqr']:.6f} ms"
        )

        print()
        print(
            "Memory OFF runtime"
        )

        print(
            f"  Mean   : "
            f"{off_stats['mean']:.6f} ms"
        )

        print(
            f"  SD     : "
            f"{off_stats['sd']:.6f} ms"
        )

        print(
            f"  Median : "
            f"{off_stats['median']:.6f} ms"
        )

        print(
            f"  IQR    : "
            f"{off_stats['iqr']:.6f} ms"
        )

        print()
        print(
            "Paired ΔT = ON - OFF"
        )

        print(
            f"  Mean   : "
            f"{delta_stats['mean']:.6f} ms"
        )

        print(
            f"  Median : "
            f"{delta_stats['median']:.6f} ms"
        )

        print(
            f"  SD     : "
            f"{delta_stats['sd']:.6f} ms"
        )

        print(
            f"  IQR    : "
            f"{delta_stats['iqr']:.6f} ms"
        )

        change_pct = data[
            "median_runtime_change_pct"
        ]

        print()

        if change_pct is not None:

            print(
                "Median runtime change "
                "(ON vs OFF): "
                f"{change_pct:+.3f}%"
            )

        ratio = data[
            "median_speed_ratio_off_over_on"
        ]

        if ratio is not None:

            print(
                "Median OFF/ON ratio: "
                f"{ratio:.6f}"
            )

        print()
        print(
            "Memory statistics:"
        )

        memory_stats = data[
            "memory_statistics"
        ]

        print(
            "  Recalls      : "
            f"{memory_stats['recalls_unique_values']}"
        )

        print(
            "  Discoveries  : "
            f"{memory_stats['discoveries_unique_values']}"
        )

        print(
            "  Hits         : "
            f"{memory_stats['hits_unique_values']}"
        )

        print(
            "  Misses       : "
            f"{memory_stats['misses_unique_values']}"
        )


# ============================================================
# Main
# ============================================================

def main():

    print()
    print("=" * 80)
    print(
        "Cognitive Optimizer "
        "Memory Ablation Experiment"
    )
    print("=" * 80)

    print(
        f"Warm-up paired runs : "
        f"{WARMUP_RUNS}"
    )

    print(
        f"Measured pairs      : "
        f"{MEASURED_RUNS}"
    )

    # ========================================================
    # Build benchmarks ONCE
    # ========================================================
    #
    # Χρησιμοποιούμε το ίδιο input circuit σε όλες
    # τις paired repetitions του ίδιου benchmark.
    # ========================================================

    vqe_circuit = (
        create_vqe_ansatz()
    )

    random_circuit = (
        create_random_circuit()
    )

    # ========================================================
    # VQE
    # ========================================================

    vqe_rows = run_benchmark(
        benchmark_name="VQE",
        circuit=vqe_circuit,
    )

    # ========================================================
    # Random
    # ========================================================

    random_rows = run_benchmark(
        benchmark_name="Random",
        circuit=random_circuit,
    )

    # ========================================================
    # Merge raw data
    # ========================================================

    all_rows = (
        vqe_rows
        + random_rows
    )

    # ========================================================
    # Save raw CSV
    # ========================================================

    save_csv(
        all_rows
    )

    # ========================================================
    # Generate summary
    # ========================================================

    summary = generate_summary(
        all_rows
    )

    # ========================================================
    # Save JSON summary
    # ========================================================

    with SUMMARY_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            summary,
            file,
            indent=4,
        )

    # ========================================================
    # Terminal output
    # ========================================================

    print_summary(
        summary
    )

    print()
    print("=" * 80)

    print(
        "Experiment completed successfully."
    )

    print(
        f"Raw results: "
        f"{RAW_RESULTS_FILE}"
    )

    print(
        f"Summary: "
        f"{SUMMARY_FILE}"
    )

    print("=" * 80)


if __name__ == "__main__":
    main()
