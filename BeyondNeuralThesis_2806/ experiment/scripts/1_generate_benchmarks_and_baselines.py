import json
import time
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import EfficientSU2
from qiskit.circuit.random import random_circuit

# Ορισμός στοχευμένου συνόλου πυλών
TARGET_BASIS_GATES = ['cx', 'rz', 'sx', 'x']

def extract_circuit_metrics(qc: QuantumCircuit) -> dict:
    """Εξάγει τα βασικά δομικά χαρακτηριστικά του κυκλώματος."""
    ops = qc.count_ops()
    return {
        "depth": qc.depth(),
        "cx_count": ops.get('cx', 0),
        "total_gates": sum(ops.values())
    }

def create_vqe_ansatz(num_qubits: int = 12, reps: int = 8) -> QuantumCircuit:
    """Δημιουργεί το VQE Hardware-Efficient Ansatz (Κύκλωμα Πλεονεκτήματος)."""
    ansatz = EfficientSU2(
        num_qubits=num_qubits,
        reps=reps,
        entanglement='linear',
        insert_barriers=False
    )
    # Αποσύνθεση σε βασικές πύλες
    qc = ansatz.decompose()
    return qc

def create_random_circuit(num_qubits: int = 10, depth: int = 20) -> QuantumCircuit:
    """Δημιουργεί τυχαίο κύκλωμα Clifford+T (Κύκλωμα Αδυναμίας)."""
    qc = random_circuit(
        num_qubits=num_qubits,
        depth=depth,
        max_operands=2,
        measure=False,
        seed=42
    )
    return qc

def evaluate_baselines(qc: QuantumCircuit, circuit_name: str) -> dict:
    """Εκτελεί τη βελτιστοποίηση του Qiskit Transpiler για Levels 1, 2 και 3."""
    results = {
        "circuit_name": circuit_name,
        "original": extract_circuit_metrics(qc)
    }

    for level in [1, 2, 3]:
        start_time = time.time()
        transpiled_qc = transpile(
            qc,
            basis_gates=TARGET_BASIS_GATES,
            optimization_level=level,
            seed_transpiler=42
        )
        elapsed_time = time.time() - start_time

        metrics = extract_circuit_metrics(transpiled_qc)
        metrics["runtime_sec"] = round(elapsed_time, 4)
        results[f"qiskit_L{level}"] = metrics

    return results

if __name__ == "__main__":
    print("--- [1/2] Δημιουργία & Αξιολόγηση VQE Ansatz (12 qubits) ---")
    vqe_qc = create_vqe_ansatz()
    vqe_baselines = evaluate_baselines(vqe_qc, "VQE_Ansatz_12q")

    print("--- [2/2] Δημιουργία & Αξιολόγηση Random Circuit (10 qubits) ---")
    rand_qc = create_random_circuit()
    rand_baselines = evaluate_baselines(rand_qc, "Random_Circuit_10q")

    # Αποθήκευση αποτελεσμάτων σε αρχείο JSON για επόμενη χρήση
    combined_results = {
        "VQE": vqe_baselines,
        "Random": rand_baselines
    }

    with open("baseline_results.json", "w", encoding="utf-8") as f:
        json.dump(combined_results, f, indent=4)

    print("\nΤα αποτελέσματα αποθηκεύτηκαν επιτυχώς στο 'baseline_results.json'.")
