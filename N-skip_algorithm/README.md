# N-Skip Issue Policy Analysis

This directory contains validation and analysis code for an **N-skip issue policy with early-out**,  
designed for power- and area-constrained out-of-order cores (e.g., little or efficiency cores).

The goal of this study is not to maximize absolute throughput, but to **identify a scan depth (N) that provides a robust performance-per-watt balance** under realistic hardware constraints.

---

## Background

A naive head-only issue policy risks missing ready instructions when the head entry is blocked.  
Conversely, scanning the full issue window increases power consumption, wiring complexity, and critical-path delay linearly with window size.

The N-skip policy addresses this trade-off by:
- Scanning only the first *N* entries in the issue queue
- Issuing the first ready instruction found
- Terminating the scan early (early-out) to minimize unnecessary switching activity

---

## Analytical Motivation

Assuming each entry is independently ready with probability *p*,  
the probability of finding at least one ready instruction within the first *N* entries is:

\[
P(\text{issue}) = 1 - (1 - p)^N
\]

This function exhibits **diminishing returns**:
- Absolute readiness probability increases with *N*
- However, the *marginal gain per additional entry* decreases monotonically

As a result, scanning deeper into the queue yields progressively smaller benefits,  
while hardware cost (power, area, timing) continues to grow approximately linearly.

---

## Simulation Models

Two complementary models are used to validate this behavior:

### Model A: Independent Readiness
- Each entry is ready independently with probability *p*
- Monte Carlo simulation across multiple seeds
- Used to validate analytical trends and statistical stability

### Model B: Multi-Cycle Queue Model
- Queue state persists across cycles
- Issued instructions are removed and new entries are inserted
- Captures more realistic scheduling behavior and temporal locality

Both models measure:
- Issue rate (instructions per cycle)
- Average power (relative units)
- Performance per watt (Perf/W)

---

## Key Result: Why N = 4

Across a wide range of readiness probabilities (*p = 0.1–0.8*) and both models:

- Increasing *N* beyond 1–2 significantly improves issue rate
- Most of the performance-per-watt benefit is already recovered by **N ≈ 4**
- Beyond **N ≈ 4**, additional scan depth yields:
  - Only marginal Perf/W improvement (often within noise)
  - No consistent advantage across workloads or readiness conditions
  - Increased hardware complexity and worst-case power cost

In other words:

> Although larger *N* can slightly increase absolute issue probability,  
> the marginal benefit becomes too small to justify the linear increase in power and complexity.

Therefore, **N = 4 emerges as a robust and conservative default**:
- Near-optimal in performance-per-watt
- Stable across different readiness regimes
- Well-aligned with timing, area, and power constraints of small OoO cores

---

---

## Notes

This repository focuses on **policy-level validation**, not full RTL implementation.  
The conclusions are intended to guide microarchitectural design choices, particularly for efficiency-oriented cores where power and simplicity dominate over peak throughput.

Further extensions (e.g., wider issue, shared functional units, or different power models) can be layered on top of this framework.
