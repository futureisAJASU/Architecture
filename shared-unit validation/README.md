# Little Core Architecture v0.41 + Toy Microarchitecture Simulator Notes

This document summarizes the current state of the **Little Core Architecture** design and the accompanying **toy microarchitecture simulator** used to validate key architectural assumptions.  
It explains:

- what the little core is trying to achieve,
- why the architecture is structured the way it is,
- what the simulator models and intentionally does **not** model,
- what bottlenecks were observed,
- what should be changed next,
- what does **not** currently need to be changed,
- and how future validation will be carried out.

The goal of this document is not to claim production-level implementation accuracy.  
Instead, it is meant to provide a **clear, technically grounded design rationale** and a **traceable validation path**.

---

# 1. Design Goal

The little core is designed as a **power-first, control-centric CPU core** intended to handle:

- always-on system work,
- lightweight background tasks,
- short UI bursts,
- and limited vector / AI-adjacent acceleration

without waking larger middle or big cores too often.

The design philosophy is intentionally different from simply building a smaller version of a big core.

The objective is **not** to maximize peak IPC at all cost.  
The objective is to maximize:

- **useful work per unit power**,
- **burst responsiveness**,
- **control-path efficiency**,
- and **predictable behavior under resource pressure**.

This is why the architecture favors:

- explicit classification early in the pipeline,
- selective queueing,
- lightweight issue logic,
- shared but power-gated expensive units,
- and aggressive downstream wake-up based on early hints.

---

# 2. High-Level Architectural Philosophy

The key design idea can be summarized as follows:

> This core is not designed to "schedule better."  
> It is designed so that **heavyweight scheduling is needed less often in the first place**.

Instead of relying on a large traditional issue scheduler, the design emphasizes:

1. **Front-end hint generation**  
   Early information is extracted from the instruction stream.

2. **Central classification and routing**  
   Instructions are explicitly classified before being placed into the most appropriate queue.

3. **Small queues + limited scan issue policy**  
   Instead of a full scheduler, queues use a simple scan-based issue policy.

4. **Selective wake-up of downstream units**  
   Shared or expensive units are only woken when upcoming work suggests they will be needed.

5. **Shared execution resources for infrequent but expensive operations**  
   FP, vector, and multiply/divide resources are not duplicated unnecessarily.

6. **Power management as a first-class architectural concern**  
   Not as an afterthought.

---

# 3. Key Architectural Structure

## 3.1 Front-End

The front-end uses:

- a lightweight branch predictor,
- a 32 KB 4-way L1I,
- fetch width sized for practical little-core throughput,
- a modest decode width,
- and early classification hints generated during or near the fetch/predecode stage.

The front-end is not meant to be as speculative or as wide as a middle or big core.  
Instead, it focuses on:

- low access energy,
- stable delivery,
- and minimizing wasted work.

### Why lightweight front-end logic?
Because on a little core, front-end power can easily dominate the useful work done by tiny bursts of system activity.

The design therefore prefers:

- smaller predictor structures,
- limited but effective BTB/history support,
- and aggressive gating of parts of the front-end when unused.

---

## 3.2 Rename and ROB-lite

The design uses a **thin rename + ROB-lite style model**.

The rename / token model is not intended to mimic a large aggressive OoO core.  
Its purpose is to provide:

- dependency tracking,
- correct producer/consumer relationships,
- and in-order retirement guarantees

without paying the full complexity cost of a traditional high-end core.

The ROB in the architecture and simulator is used primarily for:

- preserving commit order,
- tracking completion state,
- and preventing correctness from depending on issue order.

It is **not** used here as a huge speculative window optimized for maximum out-of-order extraction.

---

## 3.3 Central Dispatcher + Queue Classifier

This is one of the most important design choices.

The architecture uses a **Central Dispatcher + Queue Classifier (CD+QC)** instead of relying on each execution cluster to do its own heavy scheduling.

The dispatcher:

- examines decoded instruction class,
- selects the appropriate destination queue,
- can help trigger downstream wake-up,
- and prevents unnecessary structural ambiguity later in the pipeline.

This is important because the core intentionally avoids a heavyweight issue scheduler.

---

## 3.4 Queue Structure

The current design uses separated queues for:

- INT0
- INT1
- LSQ / load-store side
- FP scalar
- Vector / SME-like path

This queue split is intentional.

### Why split FP and Vector queues?
Earlier versions used a shared FP/VEC queue.  
That created a structural problem:

- if a VEC instruction was at the head of the queue,
- and the vector unit was busy,
- then later FP instructions in the same queue could be blocked even if the FP scalar unit was free.

That is a classic **head-of-line blocking** problem.

Since FP and vector already execute on different units, keeping them in a single issue queue provided little real benefit while introducing unnecessary blocking behavior.

Therefore:

- **shared execution cluster / shared RF / shared power domain** may still make sense,
- but **FP queue and VEC queue should be split**.

This change significantly improves structural clarity and issue behavior.

---

## 3.5 Issue Policy: Scan Width Instead of Full Scheduler

The current model uses a **scan-width-based issue policy**.

A queue does not run a full content-addressable issue scheduler.  
Instead, it scans a limited number of entries from the head:

- `scan_width = 1` means only head,
- `scan_width = 4` means head through head+3.

The first ready instruction in that scan window may issue.

This is much simpler than a full scheduler and is consistent with the little-core philosophy:

- lower energy,
- lower control complexity,
- predictable behavior,
- enough flexibility to avoid excessive stalls from a single blocked head entry.

This does **not** provide full out-of-order issue.  
It is intentionally a lightweight compromise.

---

## 3.6 LSU / Memory Side

The current architecture strongly suggests that the **LSU side is one of the most important performance bottlenecks**.

The LSU path includes:

- LSQ,
- load/store handling,
- store buffering,
- MSHR-based miss tracking,
- and interaction with the vector/AI path under QoS constraints.

A crucial design clarification is that vector/AI memory activity uses the **shared LSU path**, not a completely separate memory pipeline.

This is important for realism.

The design does not assume "free" vector memory access.  
Instead, it models vector/AI activity as sharing memory-side structures under:

- request credits,
- QoS throttling,
- and limited miss-handling resources.

---

## 3.7 Shared Expensive Units

The architecture intentionally treats some units as **expensive, bursty, and worth sharing**:

- FP scalar unit
- vector / matrix-like unit
- shared MUL / DIV
- data-queue-like assist structures for vector/AI bursts

The intended behavior is:

- mostly idle most of the time,
- fully or largely gated when empty,
- brought up in advance when early hints indicate likely upcoming use.

The important detail is that these are **not** meant to behave like permanently active throughput engines.  
They are meant to behave like **short-burst accelerators within a little-core envelope**.

---

# 4. Why a Toy Simulator Was Built

A full RTL implementation was considered too early for several reasons:

1. The architecture is still evolving.
2. It is too easy to overfit RTL toward a mistaken design.
3. Correctness verification of a partially understood OoO/ROB design is harder than writing the code itself.
4. At this stage, the main need is not gate-level fidelity but **architectural behavior validation**.

Therefore, a toy simulator was built in Python to validate the following questions:

- Does the control flow make sense?
- Do queues and issue policy behave plausibly?
- Does the split FP/VEC queue remove the expected blocking?
- Does QoS/credit throttling actually matter?
- Is ROB size a bottleneck?
- Is LSQ size the real limiter?
- Is LSU latency or throughput the actual dominant bottleneck?

The simulator is not meant to be cycle-perfect against a real CPU.  
It is meant to be **causally meaningful**.

---

# 5. What the Simulator Models

The simulator models:

- instruction classes: `INT`, `LD`, `ST`, `FP`, `VEC`
- per-class queues
- a thin dispatch/classification stage
- scoreboard-like token dependencies
- in-order retirement via ROB-lite
- per-unit latency
- LSU miss handling using MSHR counts
- vector/AI throttling through credits and LSQ pressure rules
- rough "unit on-time" as a power proxy

This is enough to examine the key behavior of the architecture without pretending to be a full production microarchitecture simulator.

---

# 6. What the Simulator Intentionally Does *Not* Model

The simulator currently does **not** attempt to model:

- full rename map tables,
- true reorder buffer semantics beyond ordered retirement,
- speculative recovery,
- branch misprediction recovery,
- realistic cache hierarchy timings,
- data forwarding networks,
- memory consistency corner cases,
- TLB behavior,
- detailed vector memory micro-ops,
- or exact ISA semantics.

This is deliberate.

The simulator exists to answer **architectural questions**, not to emulate a shipping processor.

---

# 7. Dependency Model: Why It Had to Change

An earlier version used a simplistic readiness model that could lead to deadlock-like behavior.

The core problem was:

- future writes could mark a token as not ready too early,
- causing earlier instructions to wait on values that had not yet been produced,
- effectively allowing "future producers" to block "past consumers."

That is not realistic.

To fix this, the simulator was changed to use a **versioned token model**.

## Versioned Token Model
Each architectural register maps to a current token version.

- Initial architectural state uses a set of ready tokens.
- Each writing instruction allocates a **new token version**.
- Later instructions read the latest version available at the time they are generated.
- Writeback marks that specific new token as ready.

This gives a **rename-lite** effect and guarantees that dependencies always move forward in time.

This was a major correctness improvement.

---

# 8. ROB-lite Model

The simulator uses a **ROB-lite** instead of a full ROB.

Each dispatched instruction allocates a ROB entry.

Execution may complete out of order.  
However, retirement is always in-order.

This provides two important benefits:

1. It preserves a realistic notion of ordered architectural completion.
2. It allows us to observe whether ROB pressure becomes a bottleneck.

This is enough to test whether the architecture is bottlenecked by:

- front-end dispatch,
- issue,
- LSU,
- or retirement pressure

without building a full high-end out-of-order core model.

---

# 9. Current Queue and Unit Structure in the Simulator

The current simulator configuration roughly maps to the design as follows:

- `INT0Q`: integer queue for one ALU path
- `INT1Q`: second integer queue for the other ALU path
- `LSQ`: load/store queue
- `FPQ`: floating-point scalar queue
- `VECQ`: vector queue

Execution units:
- `INT0`
- `INT1`
- `LSU`
- `FP`
- `VEC`

Key configurable parameters include:

- `scan_width`
- `dispatch_width`
- `retire_width`
- queue capacities
- ROB capacity
- unit latencies
- MSHR base and gated entries
- vector credit limit
- LSQ pressure threshold

---

# 10. Important Simulator Variables and Their Meaning

## `scan_width`
How many entries from the head of a queue can be inspected for a ready instruction.

- `1` = strict head-only issue
- `4` = head..head+3

This is the main replacement for a full issue scheduler.

---

## `dispatch_width`
How many instructions can be dispatched into queues / ROB per cycle.

This approximates front-end throughput.

---

## `retire_width`
Maximum number of instructions that can retire from the ROB each cycle.

This helps determine whether retirement becomes the next bottleneck after LSU is improved.

---

## `lat_int`, `lat_lsu`, `lat_fp`, `lat_vec`
Latencies of the execution units.

These are not intended to be final microarchitectural numbers.  
They are modeling knobs used to determine sensitivity.

---

## `lsq_cap`
LSQ depth.

Used to test whether queue depth is the limiting factor, or whether the real bottleneck is LSU service rate.

---

## `rob_cap`
ROB-lite capacity.

Used to test how much in-flight buffering is needed before retirement pressure becomes significant.

---

## `vec_credit_limit`
How many vector-side outstanding memory-like events are allowed at once.

Used to prevent vector/AI traffic from monopolizing memory-side resources.

---

## `lsq_pressure_threshold`
Threshold beyond which vector activity may be throttled to protect CPU load/store traffic.

This encodes QoS behavior.

---

## `mshr_base`, `mshr_gated`
The simulator models:
- always-available base MSHRs,
- plus gated extension entries.

This reflects the architectural idea that some miss capacity may be provisioned only when needed.

---

# 11. Experimental Results So Far

Three key experiments were performed.

---

## 11.1 Experiment A: Increase LSQ capacity (`lsq_cap=8 -> 12`)

### Result
- `lsq_full` decreased significantly
- but total cycles and IPC remained effectively unchanged
- ROB pressure increased
- integer and FP/VEC side pressure increased
- LSU remained almost fully occupied

### Interpretation
This indicates that simply increasing LSQ capacity does **not** solve the core bottleneck.

Instead, increasing LSQ depth mostly **pushes pressure downstream**:
- fewer LSQ-full events,
- but more ROB occupancy,
- more queue backpressure elsewhere,
- no meaningful throughput gain.

### Conclusion
LSQ depth is **not** the primary bottleneck in the current model.

---

## 11.2 Experiment B: Reduce LSU latency (`lat_lsu=3 -> 2`)

### Result
- total cycles dropped significantly
- IPC improved strongly (`1.279 -> 1.864`)
- LSU busy stalls were greatly reduced
- `lsq_full` dropped sharply
- `global_no_issue` dropped significantly

### Interpretation
This is the strongest signal in the current simulator.

It indicates that **LSU service rate / LSU latency is the primary bottleneck** in the current design model.

Once LSU is improved:
- the architecture exposes more instruction-level activity,
- FP/VEC pressure becomes more visible,
- and ROB pressure becomes more relevant.

### Conclusion
Improving LSU throughput or effective service latency is much more valuable than merely enlarging LSQ.

This is one of the most important findings so far.

---

## 11.3 Experiment C: Reduce vector credits (`vec_credit_limit=3 -> 1`)

### Result
Almost no visible change.

### Interpretation
This does **not** mean vector credit limits are useless.

It more likely means that, in the current workload and model:
- vector-side overlapping memory pressure is not high enough,
- or vector-side MSHR occupancy is not sustained long enough,
- so the credit limit is rarely binding.

### Conclusion
The current workload is not yet aggressive enough to stress vector-side outstanding request limits.

Future experiments should use:
- more vector-heavy workloads,
- higher vector stream probability,
- lower vector-side MSHR retirement rate,
- or more memory-intensive vector behavior

to evaluate this mechanism properly.

---

# 12. Current Bottleneck Assessment

Based on the simulator so far, the current bottleneck picture is:

## Primary bottleneck
**LSU throughput / LSU latency**

## Not currently the main bottleneck
- ROB size (in baseline)
- LSQ dependency logic
- FP/VEC shared queue structure (after queue split)
- vector credit limit (under current workload)

## Potential secondary bottlenecks once LSU improves
- FP/VEC execution occupancy
- ROB pressure
- retirement width
- dispatch / queue backpressure

---

# 13. What Needs to Change Next

The simulator results suggest the next high-value experiments and design investigations should focus on:

## 13.1 LSU-side improvement experiments
Since LSU is the strongest bottleneck, next steps should include exploring:

- lower LSU latency,
- higher LSU throughput,
- better load/store overlap,
- or slightly stronger LSU-side parallelism

before spending effort on deeper LSQs.

---

## 13.2 Retirement and ROB follow-up after LSU improvement
Once LSU latency is reduced, the next likely question becomes:

- is retirement width sufficient?
- is ROB capacity sufficient once front-end pressure is no longer naturally blocked by LSU?

Good next experiments:
- `retire_width = 4 -> 6`
- `rob_cap = 64 -> 96`

---

## 13.3 More aggressive vector stress experiments
The current vector credit tests were inconclusive.

To properly test vector QoS and credit behavior, future workloads should:
- increase vector density,
- increase vector streaming probability,
- or make vector-side memory pressure last longer.

---

# 14. What Does *Not* Need Immediate Change

Based on current results, the following do **not** currently need immediate redesign:

## 14.1 ROB = 64
ROB pressure is not the primary limiter in the baseline.

There is no reason yet to enlarge it blindly.

---

## 14.2 LSQ dependency logic
`lsq_dep_stall` remains extremely small in current experiments.

So dependency selection or issue logic on the LSQ side is not where the architecture is failing.

---

## 14.3 FP/VEC queue split
This change appears justified and should remain.

The split is structurally cleaner and avoids obvious blocking problems from a shared queue.

---

# 15. Validation Strategy Going Forward

The validation plan moving forward is:

## Stage 1: Continue toy-simulator sensitivity studies
Focus on:
- LSU latency / throughput
- ROB / retire width after LSU improvement
- vector-heavy workloads for QoS / credits

## Stage 2: Build workload classes instead of relying only on mixed random traffic
Examples:
- UI burst
- background service activity
- scalar-heavy compute
- short vector burst
- vector streaming stress
- memory-miss-heavy scenario

## Stage 3: Convert observed bottlenecks into architecture notes
Only after simulator evidence is consistent should a design change be treated as architectural direction.

## Stage 4: If the architecture stabilizes, move selected blocks toward RTL
Likely first candidates:
- Central Dispatcher + Queue Classifier
- scan-width queue issue logic
- simple ROB-lite commit
- LSQ pressure / vector throttling logic

RTL should follow stable behavior, not precede it.

---

# 16. Current Design Position

At this stage, the architecture can be described as:

> A little core that intentionally avoids heavyweight issue scheduling,  
> uses structured routing and selective wake-up,  
> and currently appears to be limited primarily by LSU throughput rather than queue depth.

This is a useful result, because it means the simulator is now exposing a meaningful bottleneck rather than collapsing under structural bugs.

---

# 17. Final Summary

The architecture and simulator have progressed beyond a purely conceptual stage.

Important steps already completed include:

- replacing unrealistic dependency handling with versioned token dependencies,
- adding ROB-lite for in-order retirement,
- splitting FP and VEC queues to remove head-of-line blocking,
- validating that LSQ depth is not the dominant limiter,
- and identifying LSU latency/throughput as the current primary bottleneck.

This does **not** prove the final architecture is optimal.

What it does prove is that:

- the control flow now behaves coherently,
- the simulator is exposing believable pressure points,
- and the architecture is now being refined through evidence instead of intuition alone.

That is exactly the stage where meaningful microarchitectural iteration begins.
