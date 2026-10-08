import importlib

cog_opt_module = importlib.import_module(
    "2_cognitive_optimizer"
)
CognitiveOptimizer = cog_opt_module.CognitiveOptimizer


benchmark_module = importlib.import_module(
    "1_generate_benchmarks_and_baselines"
)

create_vqe_ansatz = (
    benchmark_module.create_vqe_ansatz
)

create_random_circuit = (
    benchmark_module.create_random_circuit
)


def metrics(qc):
    ops = qc.count_ops()

    return {
        "gates": sum(ops.values()),
        "depth": qc.depth(),
        "cx": ops.get("cx", 0),
    }


def run_test(
    name,
    circuit,
    expected,
):
    print(f"\n{name}")
    print("-" * 50)

    # Memory ON
    optimizer_on = CognitiveOptimizer(
        use_memory=True
    )

    qc_on = optimizer_on.optimize(
        circuit
    )

    on_metrics = metrics(qc_on)

    # Memory OFF
    optimizer_off = CognitiveOptimizer(
        use_memory=False
    )

    qc_off = optimizer_off.optimize(
        circuit
    )

    off_metrics = metrics(qc_off)

    print("Memory ON")
    print(on_metrics)

    print(
        "recalls      =",
        optimizer_on.rule_recalls,
    )

    print(
        "discoveries  =",
        optimizer_on.rule_discoveries,
    )

    print(
        "hit ratio    =",
        (
            optimizer_on.memory.hits
            / (
                optimizer_on.memory.hits
                + optimizer_on.memory.misses
            )
            if (
                optimizer_on.memory.hits
                + optimizer_on.memory.misses
            )
            else 0.0
        ),
    )

    print("\nMemory OFF")
    print(off_metrics)

    print(
        "direct rules =",
        optimizer_off.direct_resolutions,
    )

    assert on_metrics == expected, (
        f"{name}: Memory ON άλλαξε "
        f"το αποτέλεσμα."
    )

    assert off_metrics == expected, (
        f"{name}: Memory OFF άλλαξε "
        f"το αποτέλεσμα."
    )

    assert on_metrics == off_metrics, (
        f"{name}: ON και OFF "
        f"δεν είναι ισοδύναμα."
    )

    print("\nPASS ✓")


def main():

    run_test(
        "VQE",
        create_vqe_ansatz(),
        {
            "gates": 520,
            "depth": 61,
            "cx": 88,
        },
    )

    run_test(
        "Random",
        create_random_circuit(),
        {
            "gates": 465,
            "depth": 120,
            "cx": 112,
        },
    )

    print(
        "\nΌλοι οι regression tests "
        "ολοκληρώθηκαν επιτυχώς."
    )


if __name__ == "__main__":
    main()
