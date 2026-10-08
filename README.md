# Cognitive Circuit Optimizer

> **A memory-augmented, quantum-inspired optimization architecture for adaptive quantum circuit rewriting.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Qiskit](https://img.shields.io/badge/Qiskit-Quantum%20Computing-purple)
![Research](https://img.shields.io/badge/Type-Research-orange)
![Beyond Neural](https://img.shields.io/badge/Project-Beyond%20Neural-black)
![Status](https://img.shields.io/badge/Status-Experimental-yellow)

---

## Overview

**Cognitive Circuit Optimizer** is an experimental optimization architecture developed as part of the undergraduate thesis:

### *Beyond Neural: A Quantum Approach to Artificial Cognition*

The project investigates whether concepts inspired by **memory, experience, recall, and adaptive decision-making** can be incorporated into quantum-circuit optimization.

Instead of treating every circuit transformation as an isolated optimization step, the optimizer maintains an **episodic memory** of previously useful transformations.

When similar optimization situations appear again, the system can recall previously discovered transformations rather than rediscovering them from scratch.

The central idea is:

```text
Quantum Circuit
      │
      ▼
Pattern / State Detection
      │
      ▼
┌──────────────────────────┐
│     Cognitive Layer      │
│                          │
│   Recall ───► Memory     │
│      │          ▲        │
│      ▼          │        │
│  Discovery ─────┘        │
└──────────────────────────┘
      │
      ▼
Transformation Selection
      │
      ▼
Circuit Rewrite
      │
      ▼
Optimized Circuit
```

---

## Motivation

Traditional quantum-circuit optimizers typically operate using predefined transformation and rewrite rules.

This project explores a different question:

> **Can an optimizer accumulate useful optimization experience and reuse it when solving future circuit-transformation problems?**

The architecture introduces a lightweight cognitive mechanism on top of conventional circuit optimization.

The objective is not to reproduce biological cognition, but to investigate whether cognitive concepts such as:

- episodic memory
- recall
- discovery
- experience reuse
- adaptive transformation selection

can provide useful computational behavior in an optimization system.

---

## Core Architecture

The optimizer operates around three primary mechanisms:

1. **Discovery**
2. **Episodic Memory**
3. **Recall**

### 1. Discovery

When the optimizer encounters a transformation that is not already represented in memory, it explores the available rewrite rules and identifies an applicable optimization.

```text
Unknown Pattern
      │
      ▼
Transformation Search
      │
      ▼
Useful Rewrite
```

Once a useful transformation is discovered, it can become part of the optimizer's reusable experience.

---

### 2. Episodic Memory

Successful transformations can be stored as reusable optimization episodes.

Conceptually:

```text
Circuit Pattern
      +
Transformation
      +
Optimization Context
      │
      ▼
Episodic Memory
```

An example discovered transformation is:

```text
MERGE_RZ
```

representing the merging of compatible consecutive `RZ` rotations.

Rather than repeatedly rediscovering the same transformation, the optimizer can store and later retrieve the corresponding optimization episode.

---

### 3. Recall

When a previously encountered optimization situation appears again, the optimizer attempts to retrieve the corresponding transformation from memory.

```text
Current Pattern
      │
      ▼
Memory Lookup
      │
   ┌──┴──┐
   │     │
  HIT   MISS
   │     │
Recall  Discovery
   │     │
   └──┬──┘
      ▼
Circuit Rewrite
```

This produces an optimization loop in which previously discovered information can influence future optimization decisions.

---

# Experimental Evaluation

Two representative quantum-circuit workloads were used to evaluate the architecture:

- a **12-qubit VQE EfficientSU2 circuit**
- a **10-qubit synthetic random circuit**

The experiments investigate both final circuit characteristics and the behavior of the memory mechanism.

---

## Benchmark 1 — VQE / EfficientSU2

### Circuit

```text
Qubits:          12
Circuit family:  EfficientSU2
```

### Cognitive Optimizer Results

| Metric | Result |
|---|---:|
| Gates | **520** |
| Depth | **61** |
| CX gates | **88** |
| Memory recalls | **107** |
| Discoveries | **1** |
| Memory hit ratio | **99.07%** |

The memory-enabled execution produced:

```text
107 recalls
1 discovery
```

corresponding to a memory hit ratio of approximately:

```text
R_hit = 107 / (107 + 1)

R_hit ≈ 0.9907
```

or approximately:

```text
99.07%
```

---

## Benchmark 2 — Random Circuit

### Circuit

```text
Qubits:          10
Circuit type:    Synthetic Random Circuit
```

### Cognitive Optimizer Results

| Metric | Result |
|---|---:|
| Gates | **465** |
| Depth | **120** |
| CX gates | **112** |
| Memory recalls | **33** |
| Discoveries | **1** |
| Memory hit ratio | **97.06%** |

The memory-enabled execution produced:

```text
33 recalls
1 discovery
```

giving:

```text
R_hit = 33 / (33 + 1)

R_hit ≈ 0.9706
```

or approximately:

```text
97.06%
```

---

# Comparison with Qiskit Optimization

For the evaluated VQE circuit, the experimental optimizer was also compared with a **Qiskit Level-3 optimization pipeline** under the project's benchmark configuration.

| Metric | Qiskit L3 | Cognitive Optimizer | Difference |
|---|---:|---:|---:|
| Gate count | 628 | **520** | **−17.2%** |
| Circuit depth | 70 | **61** | **−12.9%** |
| CX gates | 88 | **88** | **0%** |

### Gate-count difference

```text
(628 - 520) / 628 × 100 ≈ 17.2%
```

### Circuit-depth difference

```text
(70 - 61) / 70 × 100 ≈ 12.9%
```

> **Important:** These results correspond to the specific circuits, backend assumptions, transpilation configuration, rewrite rules, and experimental setup used in this project. They should not be interpreted as evidence of general superiority over Qiskit's optimization pipeline.

---

# Memory Ablation

To isolate the role of episodic memory, experiments were performed with the memory mechanism both **enabled** and **disabled**.

## VQE Circuit

```text
Memory ON
│
├── Recalls:       107
├── Discoveries:     1
└── Hit Ratio:     99.07%

Memory OFF
│
└── Direct Rules:  108
```

## Random Circuit

```text
Memory ON
│
├── Recalls:        33
├── Discoveries:     1
└── Hit Ratio:      97.06%

Memory OFF
│
└── Direct Rules:   34
```

The ablation experiments are intended to study the **behavioral contribution of reusable optimization memory**, rather than merely final circuit size.

---

# Memory Hit Ratio

The memory hit ratio is defined as:

```text
             N_recall
R_hit = ─────────────────────
         N_recall + N_discovery
```

where:

- `N_recall` = number of successful memory recalls
- `N_discovery` = number of transformations requiring discovery

A high value indicates that a large fraction of optimization decisions can be resolved using previously stored optimization experience.

For example:

```text
VQE:

R_hit = 107 / 108 ≈ 0.9907


Random Circuit:

R_hit = 33 / 34 ≈ 0.9706
```

---

# Cognitive Optimization Loop

At a high level, the architecture can be represented as:

```text
                    ┌─────────────────────┐
                    │   Quantum Circuit   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Pattern Detection │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Memory Lookup    │
                    └──────────┬──────────┘
                               │
                      ┌────────┴────────┐
                      │                 │
                     HIT               MISS
                      │                 │
                      ▼                 ▼
               ┌────────────┐    ┌────────────┐
               │   Recall   │    │ Discovery  │
               └─────┬──────┘    └─────┬──────┘
                     │                  │
                     │          Store Experience
                     │                  │
                     └─────────┬────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Transformation      │
                    │ Selection           │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Circuit Rewrite   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Optimized Circuit  │
                    └─────────────────────┘
```

---

# Research Questions

This repository explores several broader research questions:

### Can optimization algorithms learn from previous optimization episodes?

### Can reusable memory reduce repeated transformation search?

### Can optimization experience be represented independently from the original circuit?

### Can cognitive mechanisms improve adaptive circuit rewriting?

### Can memory itself become a computational resource for optimization?

### Can optimization knowledge transfer between different circuit instances?

These questions connect the project with broader research areas including:

- Quantum Computing
- Artificial Cognition
- Adaptive Optimization
- Quantum Circuit Compilation
- Memory-Augmented Algorithms
- Hybrid Quantum-Classical Systems
- Quantum Software Engineering

---

# Repository Structure

A recommended repository organization is:

```text
cognitive-circuit-optimizer/
│
├── src/
│   └── cognitive_optimizer/
│
├── experiments/
│   ├── vqe/
│   ├── random_circuit/
│   └── memory_ablation/
│
├── benchmarks/
│
├── tests/
│
├── figures/
│
├── results/
│
├── requirements.txt
├── LICENSE
└── README.md
```

The exact structure may evolve as the research implementation is cleaned, modularized, and extended.

---

# Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/cognitive-circuit-optimizer.git
cd cognitive-circuit-optimizer
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on macOS/Linux:

```bash
source .venv/bin/activate
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

---

# Running the Experiments

The repository contains experiments covering:

```text
VQE / EfficientSU2 circuits
          │
          ├── Circuit optimization
          ├── Memory-enabled execution
          └── Benchmark collection

Random synthetic circuits
          │
          ├── Circuit optimization
          ├── Memory-enabled execution
          └── Benchmark collection

Memory Ablation
          │
          ├── Memory ON
          └── Memory OFF

Validation
          │
          └── Regression testing
```

Detailed reproduction commands can be provided alongside each cleaned experiment script.

---

# Validation

The project includes regression testing to verify that optimization transformations preserve the expected circuit behavior.

```text
Regression Tests
      │
      ▼
     PASS
```

Reducing gate count or circuit depth is only useful when the transformation preserves the intended computation.

Validation is therefore treated as an essential component of the optimization pipeline.

---

# Beyond Neural

This project originated from the undergraduate thesis:

## *Beyond Neural: A Quantum Approach to Artificial Cognition*

The broader research investigated computational architectures beyond conventional neural-network paradigms and explored the intersection between:

```text
              Artificial Cognition
                       │
                       │
                       ▼
Quantum Computing ──── × ──── Adaptive Optimization
                       │
                       │
                       ▼
               Computational Memory
```

The **Cognitive Circuit Optimizer** represents an experimental implementation of this research direction.

---

# Future Work

Potential research directions include:

- confidence-weighted memory retrieval
- memory decay and forgetting mechanisms
- similarity-based episode retrieval
- larger episodic-memory spaces
- adaptive exploration strategies
- cost-aware transformation selection
- hardware-aware circuit optimization
- cross-circuit knowledge transfer
- reinforcement-based transformation policies
- learned rewrite-rule selection
- dynamic memory consolidation
- integration with larger quantum compilation pipelines
- optimization under realistic hardware constraints
- transfer of optimization experience between circuit families

A particularly interesting research direction is investigating whether optimization knowledge learned from one family of circuits can transfer to **previously unseen quantum-circuit architectures**.

---

# Citation

If you use this project or build upon its ideas in academic work, please cite the repository and associated thesis.

```bibtex
@thesis{papamichail2026beyondneural,
  author = {Nickolas-Adrian Papamichail},
  title  = {Beyond Neural: A Quantum Approach to Artificial Cognition},
  year   = {2026},
  type   = {Undergraduate Thesis}
}
```

---

# Author

## Nickolas-Adrian Papamichail

Research interests:

`Quantum Computing` · `Artificial Cognition` · `Quantum Optimization` · `Scientific Computing` · `Quantum Algorithms` · `Hybrid Quantum-Classical Systems`

---

# Disclaimer

This repository contains **experimental research software**.

The reported benchmarks represent specific experimental configurations and should not be interpreted as universal performance claims across arbitrary quantum circuits, hardware backends, compiler configurations, or optimization workloads.

The project is intended primarily for **research, experimentation, and exploration of memory-augmented optimization architectures**.

---

## GitHub Topics

Recommended topics for this repository:

`quantum-computing` `quantum-circuits` `quantum-optimization` `qiskit` `quantum-algorithms` `circuit-optimization` `quantum-compilation` `artificial-cognition` `cognitive-computing` `memory-augmented` `adaptive-optimization` `hybrid-quantum-classical` `scientific-computing` `quantum-software` `research`

---

<p align="center">
  <b>Beyond Neural</b><br>
  Exploring computation beyond conventional neural architectures.
</p>
