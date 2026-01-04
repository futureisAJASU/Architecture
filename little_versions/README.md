# Little core's previous versions

## v0.3
the basic version of Little core designs

## v0.4

This update incorporates community feedback and internal design review following **v0.3**.  
The primary focus of **v0.4** is **clarifying memory connectivity, tightening resource isolation, and improving realism of power-management assumptions**, without changing the core architectural philosophy.

---

## 1. Clarified Vector / AI Memory Access Path

### Changes
- Explicitly documented that **FP / Vector / SME-like operations use the shared LSU path**.
- Added a conceptual **Vector/FP → LSQ access interface** (control-level only, not a separate LSU).
- Diagrams now clearly show the following memory path:
  Vector / FP → (shared LSQ) → L1D → MSHR → L2
### Rationale
In **v0.22**, vector/AI execution blocks appeared visually disconnected from the memory hierarchy, leading to the incorrect assumption that vector operations bypass or duplicate the LSU.

This update makes it explicit that:
- There is **no separate memory pipeline** for vector/AI.
- All memory accesses are arbitrated through the **same Load/Store Queue (LSQ)** as scalar CPU operations.

This reflects realistic low-power CPU design constraints and avoids unnecessary duplication of AGU/LSU hardware.

---

## 2. Credit-Limited and QoS-Aware LSQ Access for Vector / AI

### Changes
- Introduced **per-class outstanding request limits (credits)** for vector/AI memory access.
- Defined a **QoS / priority policy**:
- Interactive scalar CPU loads/stores have higher priority.
- Vector/AI traffic is throttled under LSQ or MSHR pressure.
- Clarified MSHR structure as:
- **4 base entries** (always available)
- **+4 gated entries** (preferentially used by vector/AI traffic)

### Rationale
A key concern was that vector or AI workloads could monopolize memory resources and stall normal CPU execution.

The design explicitly prevents this by:
- Limiting the number of outstanding vector/AI misses.
- Ensuring foreground CPU workloads are never starved.
- Treating vector/AI execution as **best-effort, burst-oriented acceleration**, not long-running throughput compute.

---

## 3. Refined Scope and Intent of Vector / AI Execution

### Clarification
The vector/AI path is **not intended to replace an NPU**.

Target workloads include:
- Short-lived vector kernels
- Small matrix or DSP-like operations
- Cache-friendly or reuse-heavy compute

Long-running, memory-streaming AI workloads are intentionally constrained.

### Implication
This aligns with the core design goal:

> Reduce big/middle-core wakeups by handling **lightweight acceleration** efficiently on the little core.

---

## 4. Shared FP / Vector Queue Depth Adjustment

### Changes
- Increased shared FP / Vector issue queue depth to **6–8 entries**.
- Added explicit power policy:
- Fully clock-gated when empty
- Woken early via predecode / classification hints

### Rationale
Shared execution units exhibit bursty usage patterns:
- Long idle periods
- Short, dense execution windows

Increasing queue depth while keeping aggressive gating improves burst absorption without affecting idle power.

---

## 5. Cache Power Management Terminology and Assumptions Updated

### Changes
- Replaced vague “aggressive power gating” wording with:
- `way prediction`
- `way gating`
- `clock gating (default)`
- `retention for long idle (optional)`
- Explicitly stated that **full cache power-off is rare and not the default policy**.

### Rationale
Previous wording implied unrealistic cache on/off behavior.

This update aligns the design description with **industry-standard low-power cache techniques** and avoids overstating power-gating aggressiveness.

---

## 6. SME2 Handling Clarified (Standard vs. Custom Options)

### Changes
SME2 support is now documented as two alternative modeling options:

- **Option A: Standard Arm SME2**
- Requires Armv9.2-A, toolchain, and OS support
- **Option B: Custom Matrix / Vector Execution Unit**
- Same architectural intent
- Easier for research and microarchitecture exploration

### Rationale
This project focuses on **microarchitectural concepts**, not ISA lock-in.

Separating architectural intent from ISA compliance avoids confusion while keeping the design flexible.

---

## 7. Core Architectural Philosophy (Unchanged)

### Explicitly unchanged
- No traditional OoO issue scheduler added.
- Central Dispatcher + Queue Classifier remains the primary control mechanism.
- Head + N skip issue policy is preserved.
- Design emphasis remains on:
- Control-centric efficiency
- Predictable power behavior
- Burst responsiveness without brute-force width

---

## Summary

**v0.23** does not fundamentally alter the architecture.

Instead, it:
- Tightens the specification
- Eliminates ambiguity
- Adds realistic control mechanisms where concerns were raised

The design now more clearly communicates that it is:

> A power-first, control-centric little core  
> designed to stay active continuously,  
> absorb short bursts efficiently,  
> and minimize big/middle-core wakeups  
> without relying on heavyweight scheduling machinery.
