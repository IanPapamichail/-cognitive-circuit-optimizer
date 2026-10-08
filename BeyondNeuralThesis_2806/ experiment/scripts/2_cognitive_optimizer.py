"""

cognitive_optimizer.py

Created for the thesis of Nickolas Adrian Papamichail
Code co-created by Nickolas Adrian Papamichail and Gemini 3 Pro Code Assistive (Google)


Cognitive Quantum Circuit Optimizer
-----------------------------------

Ο βελτιστοποιητής εφαρμόζει ένα μικρό σύνολο αλγεβρικών
μετασχηματισμών σε κβαντικά κυκλώματα και χρησιμοποιεί
επεισοδιακή μνήμη M_e για την αναγνώριση και ανάκληση
προηγουμένως καταγεγραμμένων δομικών προτύπων.

Οι βασικοί μετασχηματισμοί είναι:

    1. MERGE_RZ
       RZ(a) · RZ(b) -> RZ(a + b)

    2. SX_TO_X
       SX · SX -> X

    3. CANCEL_X
       X · X -> I

    4. CANCEL_CX
       CX · CX -> I

Η παράμετρος use_memory επιτρέπει controlled ablation:

    CognitiveOptimizer(use_memory=True)
        -> ενεργή επεισοδιακή μνήμη

    CognitiveOptimizer(use_memory=False)
        -> ίδιοι ακριβώς κανόνες χωρίς lookup/store

Σημαντικό:
Η ενεργοποίηση ή απενεργοποίηση της μνήμης δεν πρέπει
να αλλάζει το τελικό βελτιστοποιημένο κύκλωμα.
"""

import json
import time
import importlib

import numpy as np

from qiskit import QuantumCircuit, transpile
from qiskit.converters import circuit_to_dag
from qiskit.quantum_info import hellinger_fidelity
from qiskit_aer import AerSimulator


# ============================================================
# Fake IBM Quantum Backend
# ============================================================

try:
    from qiskit_ibm_runtime.fake_provider import (  # type: ignore
        FakeEagleV2 as FakeEagle
    )

    HAS_FAKE_EAGLE = True

except ImportError:
    HAS_FAKE_EAGLE = False


# ============================================================
# Κοινό βασικό σύνολο πυλών
# ============================================================

# Όλα τα κυκλώματα μεταγλωττίζονται πρώτα σε αυτή τη βάση.
#
# CX : ελεγχόμενη πύλη X
# RZ : περιστροφή γύρω από τον άξονα Z
# SX : τετραγωνική ρίζα της X
# X  : πύλη Pauli-X

TARGET_BASIS = [
    "cx",
    "rz",
    "sx",
    "x",
]


# ============================================================
# Episodic Memory
# ============================================================

class EpisodicMemory:
    """
    Επεισοδιακή Μνήμη M_e.

    Η μνήμη αποθηκεύει αντιστοιχίσεις της μορφής:

        abstract_pattern -> rule_id

    Παράδειγμα:

        "sx:(0,):NOPARAM->sx:(0,):NOPARAM"
            ->
        "SX_TO_X"

    Το αφαιρετικό κλειδί δεν εξαρτάται από τους πραγματικούς
    αριθμούς των qubits. Έτσι το ίδιο τοπικό πρότυπο μπορεί
    να αναγνωριστεί σε διαφορετικές θέσεις του κυκλώματος.
    """

    def __init__(self):
        # Dictionary:
        # abstract_key -> rule_id
        self.memory = {}

        # Αριθμός επιτυχημένων lookups.
        self.hits = 0

        # Αριθμός αποτυχημένων lookups.
        self.misses = 0

    # --------------------------------------------------------
    # Reset
    # --------------------------------------------------------

    def reset(self):
        """
        Καθαρίζει πλήρως τη μνήμη και τους μετρητές.
        """

        self.memory.clear()
        self.hits = 0
        self.misses = 0

    # --------------------------------------------------------
    # Abstract pattern representation
    # --------------------------------------------------------

    def get_abstract_key(
        self,
        gate_sequence: list,
    ) -> str:
        """
        Δημιουργεί αφαιρετική αναπαράσταση ενός τοπικού
        προτύπου πυλών.

        Οι πραγματικοί δείκτες qubits αντικαθίστανται
        από σχετικούς δείκτες σύμφωνα με τη σειρά
        εμφάνισής τους.

        Παράδειγμα:

            CX(4, 7), CX(4, 7)

        και

            CX(1, 9), CX(1, 9)

        παράγουν την ίδια αφαιρετική δομή.

        Για τις παραμέτρους δεν αποθηκεύεται η αριθμητική
        τιμή. Αποθηκεύεται μόνο αν η πύλη διαθέτει
        παράμετρο ή όχι.
        """

        if not gate_sequence:
            return ""

        qubit_map = {}
        formatted = []

        for name, qubits, params in gate_sequence:

            # Κανονικοποίηση των qubit indices.
            #
            # Για παράδειγμα:
            # πραγματικά qubits [5, 8]
            # γίνονται [0, 1].
            norm_q = [
                qubit_map.setdefault(
                    q,
                    len(qubit_map),
                )
                for q in qubits
            ]

            # Δεν αποθηκεύουμε την πραγματική τιμή
            # της παραμέτρου.
            has_param = (
                "PARAM"
                if params and len(params) > 0
                else "NOPARAM"
            )

            formatted.append(
                f"{name}:{tuple(norm_q)}:{has_param}"
            )

        return "->".join(formatted)

    # --------------------------------------------------------
    # Memory lookup
    # --------------------------------------------------------

    def lookup(self, key: str):
        """
        Αναζητά ένα αφαιρετικό πρότυπο στη μνήμη.

        Επιστρέφει:
            rule_id αν υπάρχει το πρότυπο
            None αν το πρότυπο είναι νέο
        """

        if key in self.memory:
            self.hits += 1
            return self.memory[key]

        self.misses += 1
        return None

    # --------------------------------------------------------
    # Memory store
    # --------------------------------------------------------

    def store(
        self,
        key: str,
        rule_id: str,
    ):
        """
        Αποθηκεύει την αντιστοίχιση:

            pattern -> transformation rule
        """

        self.memory[key] = rule_id

    # --------------------------------------------------------
    # Hit ratio
    # --------------------------------------------------------

    def hit_ratio(self) -> float:
        """
        Υπολογίζει:

                    hits
        R_hit = -------------
                hits + misses
        """

        total = self.hits + self.misses

        if total == 0:
            return 0.0

        return self.hits / total


# ============================================================
# Cognitive Optimizer
# ============================================================

class CognitiveOptimizer:
    """
    Γνωστικός Βελτιστοποιητής κβαντικών κυκλωμάτων.

    Η βασική διαδικασία βελτιστοποίησης είναι ίδια
    ανεξάρτητα από την κατάσταση της μνήμης.

    use_memory=True
        Χρησιμοποιείται επεισοδιακή ανάκληση.

    use_memory=False
        Οι ίδιοι μετασχηματισμοί εφαρμόζονται χωρίς
        lookup/store στη μνήμη.

    Αυτό επιτρέπει controlled ablation experiment.
    """

    def __init__(
        self,
        use_memory: bool = True,
    ):
        # Επεισοδιακή μνήμη.
        self.memory = EpisodicMemory()

        # switch for memory ablation experiment.
        self.use_memory = use_memory

        # ----------------------------------------------
        # Experimental counters
        # -------------------------------------------

        # Πόσες φορές ένας κανόνας ανακλήθηκε
        # επιτυχώς από την επεισοδιακή μνήμη.
        self.rule_recalls = 0

        # Πόσες φορές ένα pattern ήταν νέο και
        # χρειάστηκε να καταγραφεί.
        self.rule_discoveries = 0

        # Χρησιμοποιείται μόνο όταν use_memory=False.
        #
        # Μετρά πόσες φορές χρησιμοποιήθηκε απευθείας
        # ο ήδη αναγνωρισμένος κανόνας χωρίς memory lookup.
        self.direct_resolutions = 0

    # -------------------------------------------------
    # Statistics reset
    # --------------------------------------------------

    def reset_statistics(self):
        """
        Επαναφέρει τη μνήμη και όλους τους πειραματικούς
        μετρητές στην αρχική τους κατάσταση.
        """

        self.memory.reset()

        self.rule_recalls = 0
        self.rule_discoveries = 0
        self.direct_resolutions = 0

    # --------------------------------------------------------
    # Angle addition
    # --------------------------------------------------------

    def _add_angles(
        self,
        p1,
        p2,
    ):
        """
        Συνδυάζει δύο διαδοχικές περιστροφές RZ.

        Για αριθμητικές παραμέτρους:

            RZ(p1) RZ(p2)
                ->
            RZ((p1 + p2) mod 2π)

        Αν το αποτέλεσμα είναι 0 modulo 2π,
        η περιστροφή μπορεί να εξαλειφθεί.

        Για symbolic parameters διατηρείται
        το άθροισμα p1 + p2.
        """

        if (
            isinstance(
                p1,
                (int, float, np.number),
            )
            and isinstance(
                p2,
                (int, float, np.number),
            )
        ):

            res = float(
                p1 + p2
            ) % (2 * np.pi)

            if (
                np.isclose(
                    res,
                    0.0,
                    atol=1e-7,
                )
                or np.isclose(
                    res,
                    2 * np.pi,
                    atol=1e-7,
                )
            ):
                return None

            return res

        # Symbolic parameters.
        return p1 + p2

    # --------------------------------------------------------
    # Rule resolution / Episodic recall
    # --------------------------------------------------------

    def _resolve_rule(
        self,
        pattern: list,
        expected_rule: str,
    ) -> str:
        """
        Κεντρικός μηχανισμός σύνδεσης του optimizer
        με την επεισοδιακή μνήμη.

        Δεν αποφασίζει αν ένα pattern είναι κατάλληλο
        για κάποιον μαθηματικό μετασχηματισμό.

        Η αναγνώριση αυτή εξακολουθεί να γίνεται
        από τους υπάρχοντες κανόνες της optimize().

        Η μέθοδος εξετάζει αν η ταυτότητα του
        ήδη αναγνωρισμένου κανόνα υπάρχει στη μνήμη.

        Memory OFF
        ----------
        Ο κανόνας χρησιμοποιείται άμεσα χωρίς
        lookup/store.

        Memory ON + HIT
        ----------------
        Η ταυτότητα του κανόνα ανακαλείται από
        προηγούμενη καταχώριση.

        Memory ON + MISS
        -----------------
        Το pattern είναι νέο και αποθηκεύεται
        μαζί με την ταυτότητα του κανόνα.

        Με αυτόν τον τρόπο οι αλγεβρικοί κανόνες
        παραμένουν ακριβώς ίδιοι και η μνήμη μπορεί
        να εξεταστεί ανεξάρτητα.
        """

        # ------------------------------------------------
        # Ablation mode: memory OFF
        # ------------------------------------------------

        if not self.use_memory:
            self.direct_resolutions += 1
            return expected_rule

        # ------------------------------------------------
        # Δημιουργία αφαιρετικού κλειδιού
        # ------------------------------------------------

        key = self.memory.get_abstract_key(
            pattern
        )

        # ------------------------------------------------
        # Αναζήτηση στη μνήμη
        # ------------------------------------------------

        recalled_rule = self.memory.lookup(
            key
        )

        # ------------------------------------------------
        # Memory HIT
        # ------------------------------------------------

        if recalled_rule is not None:

            self.rule_recalls += 1

            # Safety check.
            #
            # Το ίδιο αφαιρετικό pattern δεν πρέπει
            # ποτέ να αντιστοιχιστεί σε διαφορετικό
            # μετασχηματιστικο κανονα.
            if recalled_rule != expected_rule:
                raise RuntimeError(
                    "Ασυνεπής επεισοδιακή μνήμη. "
                    f"Αναμενόταν '{expected_rule}', "
                    f"αλλά ανακλήθηκε "
                    f"'{recalled_rule}'."
                )

            return recalled_rule

        # ------------------------------------------------
        # Memory MISS
        # ------------------------------------------------

        self.rule_discoveries += 1

        self.memory.store(
            key,
            expected_rule,
        )

        return expected_rule

    # --------------------------------------------------------
    # Main optimization method
    # --------------------------------------------------------

    def optimize(
        self,
        circuit: QuantumCircuit,
    ) -> QuantumCircuit:
        """
        Εφαρμόζει τον Cognitive Optimizer σε ένα
        QuantumCircuit.

        Βήματα:

        1. Μεταγλώττιση στο TARGET_BASIS.
        2. Μετατροπή σε DAG.
        3. Σάρωση των πυλών σε τοπολογική σειρά.
        4. Εφαρμογή των τοπικών κανόνων.
        5. Ανακατασκευή του βελτιστοποιημένου
           κβαντικού κυκλώματος.
        """

        # ====================================================
        # 0. Canonical basis
        # ====================================================

        # Διατηρείται ακριβώς η αρχική επιλογή
        # optimization_level=1.
        qc = transpile(
            circuit,
            basis_gates=TARGET_BASIS,
            optimization_level=1,
        )

        num_qubits = qc.num_qubits

        # ====================================================
        # 1. Circuit -> DAG
        # ====================================================

        dag = circuit_to_dag(qc)

        # Μετατρέπουμε τα DAG nodes σε απλές tuples:
        #
        # (
        #     gate_name,
        #     [qubits],
        #     [parameters]
        # )

        ops = []

        for node in dag.topological_op_nodes():

            q_indices = [
                dag.find_bit(q).index
                for q in node.qargs
            ]

            ops.append(
                (
                    node.op.name,
                    q_indices,
                    list(node.op.params),
                )
            )

        # ====================================================
        # 2. Per-qubit stacks
        # ====================================================

        # Κάθε qubit διατηρεί μία προσωρινή στοίβα
        # των πράξεων που το επηρεάζουν.
        qubit_stacks = {
            q: []
            for q in range(num_qubits)
        }

        # ====================================================
        # 3. Optimization pass
        # ====================================================

        for op in ops:

            name, qubits, params = op

            # =================================================
            # SINGLE-QUBIT RULES
            # =================================================

            if len(qubits) == 1:

                q = qubits[0]

                # ---------------------------------------------
                # RULE 1
                #
                # MERGE_RZ
                # ---------------------------------------------
                #
                # RZ rotations στο ίδιο qubit μπορούν
                # να συγχωνευτούν:
                #
                # RZ(a) RZ(b)
                #     ->
                # RZ(a + b)
                #
                # Η υλοποίηση επιτρέπει την αναζήτηση
                # προηγούμενου RZ διαμέσου CX όπου το
                # συγκεκριμένο qubit λειτουργεί ως control.
                # ---------------------------------------------

                if name == "rz":

                    idx = (
                        len(qubit_stacks[q]) - 1
                    )

                    merged = False

                    while idx >= 0:

                        prev_op = (
                            qubit_stacks[q][idx]
                        )

                        # -------------------------------------
                        # RZ μπορεί να κινηθεί διαμέσου CX
                        # όταν το q είναι control.
                        # -------------------------------------

                        if (
                            prev_op[0] == "cx"
                            and prev_op[1][0] == q
                        ):
                            idx -= 1

                        # -------------------------------------
                        # Βρέθηκε προηγούμενο RZ.
                        # -------------------------------------

                        elif prev_op[0] == "rz":

                            pattern = [
                                prev_op,
                                op,
                            ]

                            rule = self._resolve_rule(
                                pattern,
                                "MERGE_RZ",
                            )

                            # Η συνθήκη διατηρεί σαφή
                            # σύνδεση μεταξύ rule_id
                            # και transformation handler.
                            if rule == "MERGE_RZ":

                                prev_rz = (
                                    qubit_stacks[q]
                                    .pop(idx)
                                )

                                new_angle = (
                                    self._add_angles(
                                        prev_rz[2][0],
                                        params[0],
                                    )
                                )

                                # Αν new_angle=None,
                                # η συνολική περιστροφή
                                # είναι ταυτοτική.
                                if (
                                    new_angle
                                    is not None
                                ):
                                    qubit_stacks[q].insert(
                                        idx,
                                        (
                                            "rz",
                                            [q],
                                            [new_angle],
                                        ),
                                    )

                                merged = True
                                break

                        else:
                            break

                    if merged:
                        continue

                # ---------------------------------------------
                # Έλεγχος της κορυφής της στοίβας
                # ---------------------------------------------

                if qubit_stacks[q]:

                    top_op = (
                        qubit_stacks[q][-1]
                    )

                    # =========================================
                    # RULE 2
                    #
                    # SX . SX -> X
                    # =========================================

                    if (
                        name == "sx"
                        and top_op[0] == "sx"
                    ):

                        pattern = [
                            top_op,
                            op,
                        ]

                        rule = self._resolve_rule(
                            pattern,
                            "SX_TO_X",
                        )

                        if rule == "SX_TO_X":

                            # Αφαίρεση προηγούμενου SX.
                            qubit_stacks[q].pop()

                            # Αντικατάσταση SX SX με X.
                            qubit_stacks[q].append(
                                (
                                    "x",
                                    [q],
                                    [],
                                )
                            )

                            continue

                    # =========================================
                    # RULE 3
                    #
                    # X . X -> I
                    # =========================================

                    if (
                        name == "x"
                        and top_op[0] == "x"
                    ):

                        pattern = [
                            top_op,
                            op,
                        ]

                        rule = self._resolve_rule(
                            pattern,
                            "CANCEL_X",
                        )

                        if rule == "CANCEL_X":

                            # X X = I
                            #
                            # Αφαιρούμε το προηγούμενο X
                            # και δεν προσθέτουμε το νέο.
                            qubit_stacks[q].pop()

                            continue

                # Αν κανένας κανόνας δεν εφαρμόστηκε,
                # η πράξη παραμένει στη στοίβα.
                qubit_stacks[q].append(op)

            # =================================================
            # TWO-QUBIT RULES
            # =================================================

            elif (
                len(qubits) == 2
                and name == "cx"
            ):

                c, t = qubits

                # =============================================
                # RULE 4
                #
                # CX . CX -> I
                # =============================================

                if (
                    qubit_stacks[c]
                    and qubit_stacks[t]
                ):

                    top_c = (
                        qubit_stacks[c][-1]
                    )

                    top_t = (
                        qubit_stacks[t][-1]
                    )

                    # Το "is" είναι σημαντικό:
                    #
                    # θέλουμε να επιβεβαιώσουμε ότι
                    # και οι δύο στοίβες αναφέρονται
                    # στο ίδιο ακριβώς προηγούμενο
                    # CX operation object.
                    if (
                        top_c is top_t
                        and top_c[0] == "cx"
                        and top_c[1] == [c, t]
                    ):

                        pattern = [
                            top_c,
                            op,
                        ]

                        rule = self._resolve_rule(
                            pattern,
                            "CANCEL_CX",
                        )

                        if (
                            rule
                            == "CANCEL_CX"
                        ):

                            # CX CX = I.
                            qubit_stacks[c].pop()
                            qubit_stacks[t].pop()

                            continue


                # Χρησιμοποιούμε το ΙΔΙΟ tuple object
                # και στις δύο στοίβες.
                #
                # Αυτό επιτρέπει αργότερα τον έλεγχο:
                #
                # top_c is top_t
                cx_op = (
                    "cx",
                    [c, t],
                    [],
                )

                qubit_stacks[c].append(
                    cx_op
                )

                qubit_stacks[t].append(
                    cx_op
                )

        # ====================================================
        # 4. Topological reconstruction
        # ====================================================

        opt_qc = QuantumCircuit(
            num_qubits
        )

        # Δείκτης τρέχουσας θέσης
        # για κάθε qubit stack.
        pointers = {
            q: 0
            for q in range(num_qubits)
        }

        while True:

            progress = False

            for q in range(num_qubits):

                if (
                    pointers[q]
                    < len(qubit_stacks[q])
                ):

                    op = (
                        qubit_stacks[q]
                        [pointers[q]]
                    )

                    (
                        op_name,
                        op_qubits,
                        op_params,
                    ) = op

                    # -----------------------------------------
                    # Single-qubit operation
                    # -----------------------------------------

                    if len(op_qubits) == 1:

                        if op_name == "rz":
                            opt_qc.rz(
                                op_params[0],
                                op_qubits[0],
                            )

                        elif op_name == "sx":
                            opt_qc.sx(
                                op_qubits[0]
                            )

                        elif op_name == "x":
                            opt_qc.x(
                                op_qubits[0]
                            )

                        pointers[q] += 1

                        progress = True
                        break

                    # -----------------------------------------
                    # Two-qubit operation
                    # -----------------------------------------

                    elif len(op_qubits) == 2:

                        c, t = op_qubits

                        # Το CX μπορεί να τοποθετηθεί
                        # μόνο όταν και οι δύο stacks
                        # βρίσκονται στο ίδιο operation.
                        if (
                            pointers[c]
                            < len(
                                qubit_stacks[c]
                            )
                            and
                            qubit_stacks[c][
                                pointers[c]
                            ] is op
                            and
                            pointers[t]
                            < len(
                                qubit_stacks[t]
                            )
                            and
                            qubit_stacks[t][
                                pointers[t]
                            ] is op
                        ):

                            opt_qc.cx(
                                c,
                                t,
                            )

                            pointers[c] += 1
                            pointers[t] += 1

                            progress = True
                            break

            # Αν δεν τοποθετήθηκε καμία νέα πράξη,
            # η ανακατασκευή ολοκληρώθηκε.
            if not progress:
                break

        return opt_qc


# ============================================================
# Fidelity Evaluation
# ============================================================

def evaluate_fidelity(
    qc: QuantumCircuit,
    shots: int = 2000,
) -> float:
    """
    Υπολογίζει Hellinger fidelity μεταξύ:

        1. ιδανικής εκτέλεσης
        2. θορυβώδους προσομοίωσης FakeEagleV2

    Αν το κύκλωμα έχει μη δεσμευμένες παραμέτρους,
    κάθε παράμετρος λαμβάνει την τιμή 0.1.

    Σημείωση:
    Η συνάρτηση διατηρεί την αρχική μεθοδολογία
    του πειράματος.
    """

    qc_meas = qc.copy()

    # --------------------------------------------------------
    # Parameter binding
    # --------------------------------------------------------

    if qc_meas.parameters:

        param_binds = {
            p: 0.1
            for p in qc_meas.parameters
        }

        qc_meas = (
            qc_meas.assign_parameters(
                param_binds
            )
        )

    # Προσθήκη measurements.
    qc_meas.measure_all()

    # --------------------------------------------------------
    # Ideal simulation
    # --------------------------------------------------------

    ideal_sim = AerSimulator()

    ideal_transpiled = transpile(
        qc_meas,
        ideal_sim,
    )

    ideal_counts = (
        ideal_sim.run(
            ideal_transpiled,
            shots=shots,
        )
        .result()
        .get_counts()
    )

    # --------------------------------------------------------
    # Noisy simulation
    # --------------------------------------------------------

    if HAS_FAKE_EAGLE:

        noisy_sim = (
            AerSimulator.from_backend(
                FakeEagle()
            )
        )

    else:

        # Fallback μόνο αν δεν υπάρχει
        # FakeEagleV2 στο περιβάλλον.
        noisy_sim = AerSimulator()

    noisy_transpiled = transpile(
        qc_meas,
        noisy_sim,
    )

    noisy_counts = (
        noisy_sim.run(
            noisy_transpiled,
            shots=shots,
        )
        .result()
        .get_counts()
    )

    # --------------------------------------------------------
    # Hellinger fidelity
    # --------------------------------------------------------

    fidelity = hellinger_fidelity(
        ideal_counts,
        noisy_counts,
    )

    return round(
        float(fidelity),
        4,
    )


# ============================================================
# Circuit Metrics
# ============================================================

def extract_circuit_metrics(
    qc: QuantumCircuit,
) -> dict:
    """
    Εξάγει τις βασικές δομικές μετρικές ενός
    κβαντικού κυκλώματος.
    """

    ops = qc.count_ops()

    return {
        "depth": qc.depth(),
        "cx_count": ops.get(
            "cx",
            0,
        ),
        "total_gates": sum(
            ops.values()
        ),
    }


# ============================================================
# Derived Metrics
# ============================================================

def compute_derived_metrics(
    data: dict,
) -> dict:
    """
    Υπολογίζει παράγωγες μετρικές σύγκρισης μεταξύ
    Qiskit Level 3 και Cognitive Optimizer.
    """

    for circuit_key, results in data.items():

        l3 = results.get(
            "qiskit_L3",
            {},
        )

        cog = results.get(
            "cognitive_optimizer",
            {},
        )

        # ----------------------------------------------------
        # Memory hit ratio
        # ----------------------------------------------------

        hits = cog.get(
            "memory_hits",
            0,
        )

        misses = cog.get(
            "memory_misses",
            0,
        )

        total_accesses = (
            hits + misses
        )

        cog["hit_ratio_pct"] = (
            round(
                (
                    hits
                    / total_accesses
                ) * 100,
                2,
            )
            if total_accesses > 0
            else 0.0
        )

        if l3 and cog:

            # ------------------------------------------------
            # Gate reduction
            # ------------------------------------------------

            l3_gates = l3.get(
                "total_gates",
                0,
            )

            cog_gates = cog.get(
                "total_gates",
                0,
            )

            if l3_gates > 0:

                cog[
                    "gate_reduction_vs_l3_pct"
                ] = round(
                    (
                        (
                            l3_gates
                            - cog_gates
                        )
                        / l3_gates
                    )
                    * 100,
                    2,
                )

            # ------------------------------------------------
            # Depth reduction
            # ------------------------------------------------

            l3_depth = l3.get(
                "depth",
                0,
            )

            cog_depth = cog.get(
                "depth",
                0,
            )

            if l3_depth > 0:

                cog[
                    "depth_reduction_vs_l3_pct"
                ] = round(
                    (
                        (
                            l3_depth
                            - cog_depth
                        )
                        / l3_depth
                    )
                    * 100,
                    2,
                )

            # ------------------------------------------------
            # Raw compilation-time ratio
            # ------------------------------------------------
            #
            # Προσοχή:
            # Η τιμή αυτή είναι περιγραφική.
            # Δεν αποτελεί από μόνη της απόδειξη
            # ασυμπτωτικής επιτάχυνσης.

            l3_time = l3.get(
                "runtime_sec",
                0.0,
            )

            cog_time = cog.get(
                "runtime_sec",
                0.0,
            )

            if cog_time > 0:

                cog[
                    "compilation_speedup_factor"
                ] = round(
                    l3_time
                    / cog_time,
                    2,
                )

    return data


# ============================================================
# Layer Scaling Experiment
# ============================================================

def run_layer_scaling_experiment():
    """
    Εκτελεί την υπάρχουσα ανάλυση κλιμάκωσης
    σε VQE ansatz με 1, 2, 4 και 8 repetitions.

    Σημαντικό:
    Το experiment καταγράφει εμπειρικό χρόνο και
    memory statistics.

    Ο χρόνος δενερμηνεύεται από μόνος του
    ως απόδειξη O(1) συνολικής πολυπλοκότητας.
    """

    try:

        benchmark_module = (
            importlib.import_module(
                "1_generate_benchmarks_and_baselines"
            )
        )

        create_vqe = (
            benchmark_module
            .create_vqe_ansatz
        )

    except ImportError:

        print(
            "\n[Σφάλμα]: Δεν βρέθηκε το "
            "'1_generate_benchmarks_and_baselines.py'."
        )

        return

    print(
        "\n--- Πείραμα Κλιμάκωσης Layers VQE "
        "(Memory Scaling Analysis) ---"
    )

    print(
        f"{'Layers':<8} | "
        f"{'Total Gates':<12} | "
        f"{'Hits':<8} | "
        f"{'Misses':<8} | "
        f"{'Hit Ratio':<10} | "
        f"{'Time (sec)':<10}"
    )

    print("-" * 78)

    # Διατηρείται η υπάρχουσα συμπεριφορά:
    # ένας optimizer χρησιμοποιείται για τη
    # διαδοχική εκτέλεση των layer configurations.
    opt_engine = CognitiveOptimizer(
        use_memory=True
    )

    for reps in [
        1,
        2,
        4,
        8,
    ]:

        qc = create_vqe(
            reps=reps
        )

        start = time.perf_counter()

        opt_qc = (
            opt_engine.optimize(qc)
        )

        elapsed = (
            time.perf_counter()
            - start
        )

        hits = (
            opt_engine.memory.hits
        )

        misses = (
            opt_engine.memory.misses
        )

        ratio = (
            opt_engine.memory.hit_ratio()
            * 100
        )

        total_gates = sum(
            opt_qc
            .count_ops()
            .values()
        )

        print(
            f"{reps:<8} | "
            f"{total_gates:<12} | "
            f"{hits:<8} | "
            f"{misses:<8} | "
            f"{ratio:8.2f}% | "
            f"{elapsed:.6f}s"
        )


# ============================================================
# Main Evaluation
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Baseline results
    # --------------------------------------------------------

    try:

        with open(
            "baseline_results.json",
            "r",
            encoding="utf-8",
        ) as file:

            baseline_data = json.load(
                file
            )

    except FileNotFoundError:

        print(
            "Σφάλμα: Δεν βρέθηκε το "
            "'baseline_results.json'."
        )

        raise SystemExit(1)

    # --------------------------------------------------------
    # Benchmark generator
    # --------------------------------------------------------

    benchmark_module = (
        importlib.import_module(
            "1_generate_benchmarks_and_baselines"
        )
    )

    create_vqe_ansatz = (
        benchmark_module
        .create_vqe_ansatz
    )

    create_random_circuit = (
        benchmark_module
        .create_random_circuit
    )

    benchmarks = {

        "VQE": (
            "VQE_Ansatz_12q",
            create_vqe_ansatz(),
        ),

        "Random": (
            "Random_Circuit_10q",
            create_random_circuit(),
        ),
    }

    # Αντιγραφή των baseline αποτελεσμάτων.
    final_results = (
        baseline_data.copy()
    )

    print(
        "--- Εκτέλεση Γνωστικής "
        "Βελτιστοποίησης ---"
    )

    # ========================================================
    # Benchmark loop
    # ========================================================

    for key, (
        name,
        qc,
    ) in benchmarks.items():

        print(
            f"\n[Επεξεργασία]: {name}"
        )

        # Memory ON για την κύρια αξιολόγηση.
        cognitive_opt = CognitiveOptimizer(
            use_memory=True
        )

        # ----------------------------------------------------
        # Optimization runtime
        # ----------------------------------------------------

        start_time = (
            time.perf_counter()
        )

        opt_qc = (
            cognitive_opt.optimize(qc)
        )

        elapsed_time = (
            time.perf_counter()
            - start_time
        )

        # ----------------------------------------------------
        # Structural metrics
        # ----------------------------------------------------

        metrics = (
            extract_circuit_metrics(
                opt_qc
            )
        )

        metrics[
            "runtime_sec"
        ] = round(
            elapsed_time,
            6,
        )

        # ----------------------------------------------------
        # Memory metrics
        # ----------------------------------------------------

        metrics[
            "memory_hits"
        ] = (
            cognitive_opt.memory.hits
        )

        metrics[
            "memory_misses"
        ] = (
            cognitive_opt.memory.misses
        )

        metrics[
            "rule_recalls"
        ] = (
            cognitive_opt.rule_recalls
        )

        metrics[
            "rule_discoveries"
        ] = (
            cognitive_opt.rule_discoveries
        )

        metrics[
            "memory_hit_ratio"
        ] = round(
            cognitive_opt
            .memory
            .hit_ratio(),
            6,
        )

        # ----------------------------------------------------
        # Fidelity
        # ----------------------------------------------------

        print(
            "Υπολογισμός Πιστότητας "
            "Θορύβου (Fidelity)..."
        )

        metrics[
            "fidelity"
        ] = evaluate_fidelity(
            opt_qc
        )

        # ----------------------------------------------------
        # Qiskit Level 3 comparison
        # ----------------------------------------------------

        l3_qc = transpile(
            qc,
            basis_gates=TARGET_BASIS,
            optimization_level=3,
        )

        final_results[
            key
        ][
            "qiskit_L3"
        ][
            "fidelity"
        ] = evaluate_fidelity(
            l3_qc
        )

        # ----------------------------------------------------
        # Store cognitive results
        # ----------------------------------------------------

        final_results[
            key
        ][
            "cognitive_optimizer"
        ] = metrics

        # ----------------------------------------------------
        # Console diagnostics
        # ----------------------------------------------------

        print(
            f"Total gates     : "
            f"{metrics['total_gates']}"
        )

        print(
            f"Depth           : "
            f"{metrics['depth']}"
        )

        print(
            f"CX count        : "
            f"{metrics['cx_count']}"
        )

        print(
            f"Memory hits     : "
            f"{metrics['memory_hits']}"
        )

        print(
            f"Memory misses   : "
            f"{metrics['memory_misses']}"
        )

        print(
            f"Rule recalls    : "
            f"{metrics['rule_recalls']}"
        )

        print(
            f"Rule discoveries: "
            f"{metrics['rule_discoveries']}"
        )

        print(
            f"Hit ratio       : "
            f"{metrics['memory_hit_ratio'] * 100:.2f}%"
        )

    # ========================================================
    # Derived metrics
    # ========================================================

    final_results = (
        compute_derived_metrics(
            final_results
        )
    )

    # ========================================================
    # Save results
    # ========================================================

    with open(
        "final_evaluation_results.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            final_results,
            file,
            indent=4,
        )

    print(
        "\nΤα τελικά αποτελέσματα "
        "αποθηκεύτηκαν στο "
        "'final_evaluation_results.json'."
    )

    # ========================================================
    # Existing layer-scaling experiment
    # ========================================================

    run_layer_scaling_experiment()
