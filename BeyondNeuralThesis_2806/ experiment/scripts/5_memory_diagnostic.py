"""
5_memory_diagnostic.py

Diagnostic script για την επεισοδιακή μνήμη του CognitiveOptimizer.

Στόχος:
- Να ελέγξει ποια αφαιρετικά patterns αποθηκεύονται.
- Να δείξει ποιος transformation rule αντιστοιχεί σε κάθε pattern.
- Να επιβεβαιώσει τον αριθμό discoveries, recalls, hits και misses.
- Να συγκρίνει VQE και Random benchmark χωρίς να αλλάζει τον optimizer.

Το script δεν εκτελεί νέο optimization logic.
Χρησιμοποιεί τον υπάρχοντα CognitiveOptimizer όπως είναι.
"""

import importlib

cog_opt_module = importlib.import_module(
    "2_cognitive_optimizer"
)
CognitiveOptimizer = cog_opt_module.CognitiveOptimizer


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
# Helper functions
# ============================================================

def extract_metrics(qc) -> dict:
    """
    Επιστρέφει τις βασικές δομικές μετρικές
    του βελτιστοποιημένου κυκλώματος.
    """

    ops = qc.count_ops()

    return {
        "gates": sum(ops.values()),
        "depth": qc.depth(),
        "cx": ops.get("cx", 0),
    }


def print_memory_contents(
    optimizer: CognitiveOptimizer,
) -> None:
    """
    Εμφανίζει ολόκληρο το περιεχόμενο της
    επεισοδιακής μνήμης.

    Κάθε καταχώριση έχει μορφή:

        rule_id -> abstract_key
    """

    memory = optimizer.memory.memory

    print("\nStored episodic memories")
    print("-" * 80)

    if not memory:
        print("Η μνήμη είναι κενή.")
        return

    for index, (key, rule) in enumerate(
        memory.items(),
        start=1,
    ):
        print(
            f"[{index}] Rule: {rule}"
        )
        print(
            f"    Key : {key}"
        )
        print()


def print_rule_distribution(
    optimizer: CognitiveOptimizer,
) -> None:
    """
    Μετρά πόσες αποθηκευμένες καταχωρίσεις
    αντιστοιχούν σε κάθε rule_id.
    """

    distribution = {}

    for rule in optimizer.memory.memory.values():
        distribution[rule] = (
            distribution.get(rule, 0) + 1
        )

    print("\nStored rule distribution")
    print("-" * 80)

    if not distribution:
        print("Δεν υπάρχουν αποθηκευμένοι κανόνες.")
        return

    for rule, count in sorted(
        distribution.items()
    ):
        print(
            f"{rule:<15} : {count}"
        )


def run_diagnostic(
    benchmark_name: str,
    circuit,
) -> None:
    """
    Εκτελεί τον CognitiveOptimizer με Memory ON
    και εμφανίζει αναλυτικά το περιεχόμενο της μνήμης.
    """

    print("\n")
    print("=" * 80)
    print(
        f"MEMORY DIAGNOSTIC — {benchmark_name}"
    )
    print("=" * 80)

    # ========================================================
    # Νέος optimizer για κάθε benchmark
    # ========================================================
    #
    # Αυτό είναι σημαντικό.
    #
    # Δεν θέλουμε η μνήμη του VQE να επηρεάσει
    # το Random benchmark ή αντίστροφα.

    optimizer = CognitiveOptimizer(
        use_memory=True
    )

    # ========================================================
    # Optimization
    # ========================================================

    optimized_circuit = optimizer.optimize(
        circuit
    )

    # ========================================================
    # Circuit metrics
    # ========================================================

    metrics = extract_metrics(
        optimized_circuit
    )

    print("\nOptimized circuit metrics")
    print("-" * 80)

    print(
        f"Total gates       : "
        f"{metrics['gates']}"
    )

    print(
        f"Depth             : "
        f"{metrics['depth']}"
    )

    print(
        f"CX count          : "
        f"{metrics['cx']}"
    )

    # ========================================================
    # Memory statistics
    # ========================================================

    hits = optimizer.memory.hits
    misses = optimizer.memory.misses
    total_accesses = hits + misses

    hit_ratio = (
        hits / total_accesses
        if total_accesses > 0
        else 0.0
    )

    print("\nMemory statistics")
    print("-" * 80)

    print(
        f"Memory hits       : {hits}"
    )

    print(
        f"Memory misses     : {misses}"
    )

    print(
        f"Total accesses    : {total_accesses}"
    )

    print(
        f"Rule recalls      : "
        f"{optimizer.rule_recalls}"
    )

    print(
        f"Rule discoveries  : "
        f"{optimizer.rule_discoveries}"
    )

    print(
        f"Stored patterns   : "
        f"{len(optimizer.memory.memory)}"
    )

    print(
        f"Hit ratio         : "
        f"{hit_ratio:.6f}"
    )

    print(
        f"Hit ratio (%)     : "
        f"{hit_ratio * 100:.2f}%"
    )

    # ========================================================
    # Consistency checks
    # ========================================================

    print("\nConsistency checks")
    print("-" * 80)

    # Κάθε miss πρέπει να αντιστοιχεί σε discovery.
    misses_equal_discoveries = (
        optimizer.memory.misses
        == optimizer.rule_discoveries
    )

    print(
        "misses == discoveries : "
        f"{misses_equal_discoveries}"
    )

    # Κάθε hit πρέπει να αντιστοιχεί σε recall.
    hits_equal_recalls = (
        optimizer.memory.hits
        == optimizer.rule_recalls
    )

    print(
        "hits == recalls        : "
        f"{hits_equal_recalls}"
    )

    # Ο αριθμός stored patterns πρέπει λογικά
    # να ισούται με τα unique discoveries.
    stored_equal_discoveries = (
        len(optimizer.memory.memory)
        == optimizer.rule_discoveries
    )

    print(
        "stored == discoveries  : "
        f"{stored_equal_discoveries}"
    )

    # ========================================================
    # Full episodic memory dump
    # ========================================================

    print_memory_contents(
        optimizer
    )

    # ========================================================
    # Rule distribution
    # ========================================================

    print_rule_distribution(
        optimizer
    )


# ============================================================
# Main
# ============================================================

def main():

    print(
        "\nCognitive Optimizer "
        "Episodic Memory Diagnostic"
    )

    # ========================================================
    # VQE benchmark
    # ========================================================

    vqe_circuit = create_vqe_ansatz()

    run_diagnostic(
        benchmark_name="VQE",
        circuit=vqe_circuit,
    )

    # ========================================================
    # Random benchmark
    # ========================================================

    random_circuit = (
        create_random_circuit()
    )

    run_diagnostic(
        benchmark_name="Random",
        circuit=random_circuit,
    )

    print("\n")
    print("=" * 80)
    print(
        "Diagnostic completed successfully."
    )
    print("=" * 80)


if __name__ == "__main__":
    main()
