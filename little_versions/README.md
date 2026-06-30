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

**v0.4** does not fundamentally alter the architecture.

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

## v0.5 Direction: SME-like Execution Moved to Cluster-Level Shared Resource

The previous diagram could be interpreted as placing Vector/SME2-like execution directly inside the little core pipeline.

In the revised model, the little core retains only lightweight FP/SIMD capability, while heavier SME-like or AI-oriented execution is modeled as a cluster-shared assist engine.

This reduces core-local complexity, avoids excessive LSQ/MSHR pressure inside the little core, and better matches the intended role of the little core as a low-power background and burst-response core.

## v0.51

![Little Core v0.51 Diagram](./little_v0.51.jpg)

v0.51 refines the Little Core architecture into a more coherent **control-centric enhanced efficiency core**.

This revision focuses on clarifying execution-resource ownership, reducing unnecessary contention around shared execution units, and improving short-burst responsiveness without turning the core into a full middle-class OoO design.

The major changes are:

- Integer MUL is moved back into the core-local INT execution path.
- DIV is separated as a pair-shared long-latency execution unit.
- FP/SIMD resources are modeled as pair-shared execution resources.
- DIV and FP/SIMD use **per-core request queues**, while the execution backend is shared by a 2-core pair.
- Heavy Vector / SME-like / Matrix execution is clarified as a cluster-shared resource.
- LD/ST Queue is expanded to reduce memory-side bottlenecks.
- ROB capacity is revised to a 64-entry base with a 16-entry gated extension.
- Frontend width remains 3-wide to preserve the power-first design goal.

---

## 1. Core Positioning Clarified

### Changes

v0.51 clarifies that this design is not intended to be a minimal in-order LITTLE core.

Instead, it is positioned as a:

> control-centric enhanced efficiency core  
> placed between traditional in-order LITTLE cores  
> and full middle-class OoO cores.

### Rationale

Traditional LITTLE cores prioritize minimum area and minimum power through conservative in-order execution.

This project intentionally explores a slightly more aggressive design point:

- 3-wide frontend
- thin rename
- compact ROB
- Central Dispatcher + Queue Classifier
- Head + N skip issue policy
- distributed queues instead of a heavyweight centralized OoO scheduler

The goal is not maximum sustained throughput.

The goal is to improve:

- short-burst responsiveness
- UI / OS service latency
- background task efficiency
- middle-core wakeup reduction

while keeping the design much smaller and simpler than a true middle core.

---

## 2. Frontend Kept at 3-wide

### Changes

- Fetch remains 32B/cycle.
- Decode remains 3-wide.
- Thin & Light Rename remains 3-wide.
- Central Dispatcher + Queue Classifier remains max 3/cycle.
- The previous idea of widening decode to 4-wide is not adopted.

### Rationale

This architecture does not rely on a large centralized OoO issue scheduler.

Instead, it uses:

- early predecode hints
- Central Dispatcher + Queue Classifier
- execution-class queues
- Head + N skip issue
- long-latency offload
- small distributed queue structures

Because decoded operations are quickly classified and pushed into execution-specific queues, the design does not need to over-widen decode simply to hide backend bubbles.

The important factor is not raw frontend width, but keeping each execution queue sufficiently supplied.

Thus, 3-wide decode remains a better balance for this power-first design.

---

## 3. Branch Predictor Updated and Retained

### Changes

The branch predictor is defined as:

- **micro-TAGE** as the main predictor
- **tiny perceptron** as a selective corrector
- confidence-based selective override policy

The intended behavior is:

```text
Fast path:
micro-TAGE

Correction path:
tiny perceptron

Override:
only when micro-TAGE confidence is low
and perceptron confidence is high
```

The 80/20 notation should be interpreted as an involvement policy, not a hard area or accuracy ratio:

```text
~80% fast micro-TAGE path
~20% selective perceptron correction target
```

### Rationale

A pure gshare-style predictor is simple but too limited for this design point.

micro-TAGE provides a stronger and more modern baseline predictor, while a tiny perceptron corrector helps with harder correlated branches without requiring a full-scale high-power predictor.

This fits the design goal of improving real-world responsiveness while keeping predictor cost under control.

---

## 4. ROB Revised to 64 + 16 Gated Entries

### Changes

ROB capacity is revised from a fixed 64-entry structure to:

```text
64 base entries
+16 gated extension entries
80 entries max
```

### Rationale

The core still keeps a compact base ROB to preserve efficiency.

However, with:

- 12-entry LD/ST Queue
- pair-shared FP/SIMD backend
- pair-shared DIV backend
- MSHR 4+4
- Head + N queue-based issue

the core benefits from slightly more in-flight capacity during burst or memory-pressure scenarios.

The 16-entry gated extension provides additional window capacity only when needed, while allowing the base design to remain power-conscious during normal low-pressure execution.

This matches the same design philosophy used by the gated MSHR extension.

---

## 5. INT Execution Revised

### Changes

Integer execution is now split into:

```text
INT0 Queue
10 entries
→ full-stack ALU + INT MUL

INT1 Queue
6 entries
→ light ALU
```

The full-stack ALU handles:

- normal integer operations
- branch compare
- complex shift / bit operations
- integer MUL

The light ALU handles:

- simple add/sub
- simple logic
- simple shifts
- lightweight integer operations

### Rationale

INT0 is the main integer execution path and is expanded to 10 entries to better absorb bursty integer work and complex operations.

INT1 remains smaller and simpler to preserve area and power efficiency.

This keeps the common integer path core-local and predictable while still allowing the backend to avoid unnecessary centralized scheduling complexity.

---

## 6. Integer MUL Moved Back to Core-Local INT Execution

### Changes

- Removed integer MUL from the previous shared MUL/DIV concept.
- Added integer MUL capability to the core-local full-stack INT execution path.
- Integer MUL is now treated as part of the core-local INT0 execution path.

### Rationale

Integer MUL is much more common than integer DIV.

It appears in:

- address / index calculations
- loop arithmetic
- hashing
- compression
- web / scripting workloads
- general integer-heavy code

Sharing integer MUL across two cores could introduce unnecessary arbitration, routing, and latency overhead for a relatively common operation.

Unlike FP/SIMD or DIV, integer MUL is small enough and common enough to justify keeping it core-local.

This avoids small but frequent stalls in the INT execution path.

---

## 7. DIV Separated as Pair-Shared Long-Latency Unit

### Changes

- Replaced the previous shared MUL/DIV block with a dedicated pair-shared DIV unit.
- DIV is modeled as a long-latency offload-style unit.
- Each core keeps its own small DIV request queue.
- The actual DIV execution backend is shared by a 2-core pair.

Recommended notation:

```text
Pair-shared DIV
6-entry request queue per core
core-id tagged entries
```

For a 2-core pair:

```text
Core 0 DIV request queue: 6 entries
Core 1 DIV request queue: 6 entries
Shared DIV execution backend: 1 pair-shared unit
Total pending DIV requests per pair: 12 entries
```

### Rationale

Integer DIV has very different characteristics from integer MUL:

- low usage frequency
- long latency
- relatively complex implementation
- poor utilization if duplicated per core

Because DIV already takes many cycles, the relative impact of pair-sharing is smaller than it would be for MUL.

This makes DIV a good candidate for 2-core shared execution.

Using per-core request queues also avoids one core monopolizing the shared queue capacity before arbitration.

---

## 8. Pair-Shared FP/SIMD Execution

### Changes

- FP / Vector resources are clarified as pair-shared execution resources.
- Each core keeps its own FP/SIMD request queue.
- The FP/SIMD execution backend is shared by a 2-core pair.
- FP/SIMD execution is dynamically allocated between the two cores.
- The shared backend remains power-gated / clock-gated when idle.

Recommended notation:

```text
Pair-shared FP/SIMD
6-entry request queue per core
dynamic QoS + gated execution
```

For a 2-core pair:

```text
Core 0 FP/SIMD request queue: 6 entries
Core 1 FP/SIMD request queue: 6 entries
Shared FP/SIMD execution backend: pair-shared
Total pending FP/SIMD requests per pair: 12 entries
```

### Rationale

FP/SIMD execution hardware is larger and less continuously utilized than simple integer execution hardware.

A pair-shared design allows:

- reduced duplicated area
- better average utilization
- lower idle power
- more flexible burst allocation

When only one core in the pair is actively using FP/SIMD, it may temporarily use more of the shared execution capacity.

When both cores are active, QoS / arbitration logic distributes access and prevents starvation.

This is more area-efficient than duplicating a full FP/SIMD block per little core.

The key distinction is:

```text
Queues: per-core
Execution backend: pair-shared
```

This keeps queueing local and predictable while still reducing duplicated execution hardware.

---

## 9. Heavy Vector / SME-like / Matrix Execution Clarified as Cluster-Shared

### Changes

Heavy vector / matrix execution is not treated as a fully replicated core-local datapath.

The design distinguishes:

```text
MUL: per-core
DIV: pair-shared
FP/SIMD: pair-shared
Heavy Vector / Matrix: cluster-shared
```

The Vector/SME-like path in the diagram should be interpreted as a logical interface or lightweight vector path.

Heavier matrix-style execution may be mapped to a cluster-shared assist engine near the shared L2 / cluster-level logic.

### Rationale

Heavy vector or SME-like matrix execution can create significant pressure on:

- LSQ
- MSHR
- L1D / L2 bandwidth
- operand buffering
- shared interconnect resources

Replicating such resources inside every little core would conflict with the low-power and area-efficient design goal.

Instead, v0.51 treats heavy vector / matrix execution as a cluster-level shared assist path.

The core-local vector path should not be interpreted as a fully replicated heavy matrix engine.

---

## 10. LD/ST Queue Expanded

### Changes

- LD/ST Queue increased to 12 entries.
- Store Buffer remains 16 entries.
- L1D remains 64KB.
- MSHR remains:

```text
4 base entries
+4 gated extension entries
8 entries max
```

### Rationale

As the design becomes more capable, memory-side pressure becomes a more likely bottleneck.

The LD/ST path must absorb:

- address-generation delay
- store-load dependency checks
- store buffer pressure
- L1D misses
- MSHR backpressure
- shared-engine pressure

Expanding the LD/ST Queue to 12 entries improves tolerance against short memory-side stalls without making the design feel like a full middle core.

This is a small but useful scaling step for the enhanced efficiency-core direction.

---

## 11. Memory Path Clarified

### Changes

The LD/ST path is clarified as:

```text
LD/ST Queue
→ AGU
→ LSQ
  ├─ Load Queue / Load Logic → L1D → MSHR → Fill Path → L2
  └─ Store Buffer → L1D
```

Store Buffer address compare / forwarding is treated as a side path to Load Logic.

### Rationale

The previous diagram could be misread as routing loads through the Store Buffer.

v0.51 clarifies that loads and stores are managed through the LSQ, with the Store Buffer providing store commit and forwarding / address-compare support.

This better reflects the intended simplified load-store ordering model.

---

## 12. Cache and Page-Size Assumptions

### Changes

The cache hierarchy is described as:

```text
64KB L1I, 4-way
64KB L1D
Shared L2, 512KB–1MB per cluster
MSHR 4 + 4 gated extension
```

The L1I choice is optimized around 16KB page configurations.

### Rationale

With 64B cache lines:

```text
64KB L1I / 4-way / 64B line = 256 sets
index bits = 8
offset bits = 6
index + offset = 14 bits
```

A 16KB page has a 14-bit page offset.

This makes the 64KB 4-way L1I configuration page-offset friendly under 16KB-page assumptions.

This does not remove the need for careful synonym / alias handling in systems that support smaller page sizes, but it gives the chosen L1I size a clear mobile-oriented rationale.

---

## 13. Cluster-Level QoS / Credit Control

### Changes

v0.51 keeps cluster-level QoS / credit control for shared resources.

The policy is:

```text
Scalar CPU LD/ST priority
Shared engine requests throttled under LSQ / MSHR / L2 pressure
```

### Rationale

Shared execution resources must not starve scalar CPU work.

QoS / credit control prevents:

- shared FP/SIMD traffic from monopolizing backend capacity
- shared engine requests from creating excessive memory pressure
- heavy vector / matrix requests from blocking foreground scalar work

The design remains scalar-first and responsiveness-first.

---

## 14. Updated Resource Ownership Summary

v0.51 defines execution-resource ownership as follows:

```text
Per-core resources:
- frontend
- small BTB
- BPU
- prefetcher
- 64KB L1I
- fetch / decode
- thin rename
- ROB 64 + 16 gated
- Central Dispatcher + Queue Classifier
- INT0 Queue, 10 entries
- INT1 Queue, 6 entries
- LD/ST Queue, 12 entries
- full-stack ALU + INT MUL
- light ALU
- AGU / LSQ
- Load Queue / Load Logic
- Store Buffer, 16 entries
- 64KB L1D

Pair-shared resources:
- DIV execution backend
- FP/SIMD execution backend

Per-core queues feeding pair-shared resources:
- DIV request queue, 6 entries per core
- FP/SIMD request queue, 6 entries per core

Cluster-shared resources:
- shared L2, 512KB–1MB per cluster
- heavy Vector / SME-like / Matrix assist logic
- cluster-level QoS / credit control
```

---

## 15. Core Philosophy

v0.51 reinforces the architecture as:

> a power-first, control-centric enhanced little core  
> designed to remain lightweight,  
> absorb short bursts efficiently,  
> reduce middle/big core wakeups,  
> and avoid heavyweight centralized OoO scheduling.

The design is intentionally more capable than a minimal in-order LITTLE core, but still avoids the complexity, power, and area cost of a full middle core.

It relies on:

- compact frontend width
- small distributed queues
- early classification
- Head + N skip issue
- core-local common integer execution
- pair-shared large / bursty execution resources
- cluster-shared heavy vector / matrix resources

---

## Summary

v0.51 is a cleanup and scaling revision.

It does not change the core philosophy.

Instead, it improves consistency by:

- keeping common integer MUL local
- sharing only long-latency DIV execution
- giving DIV a 6-entry request queue per core
- modeling FP/SIMD execution as pair-shared
- giving FP/SIMD a 6-entry request queue per core
- moving heavy Vector / Matrix intent to the cluster-shared level
- expanding LD/ST Queue to 12 entries
- increasing ROB capacity to 64 + 16 gated entries
- keeping frontend width at 3-wide

The result is a cleaner enhanced efficiency-core design:

```text
MUL local
DIV pair-shared
FP/SIMD pair-shared
Heavy Vector / Matrix cluster-shared
LD/ST widened
ROB lightly extended
Frontend still compact
```
