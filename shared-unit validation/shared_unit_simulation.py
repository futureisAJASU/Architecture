from __future__ import annotations
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple
from collections import deque, defaultdict
import random

# ============================================================
# 0) Core idea
# ------------------------------------------------------------
# - Scoreboard-lite token dependencies
# - Versioned tokens (rename-lite) so future writers never block past readers
# - Execution may complete out-of-order
# - Retire remains in-order via ROB-lite
# - Ready = all read tokens are ready
# - Writeback sets write tokens ready and wakes up dependents
# - FP and VEC queues are split to avoid HOL blocking
# ============================================================


# -----------------------------
# Instruction model
# -----------------------------
@dataclass
class Instr:
    iid: int
    cls: str  # "INT", "LD", "ST", "FP", "VEC"
    reads: List[int]
    writes: List[int]
    mem_op: bool = False
    mem_miss: bool = False
    age: int = 0

    def __repr__(self) -> str:
        return (
            f"Instr(iid={self.iid}, cls={self.cls}, "
            f"r={self.reads}, w={self.writes}, miss={self.mem_miss})"
        )


# -----------------------------
# Scoreboard-lite tokens
# -----------------------------
@dataclass
class Scoreboard:
    token_ready: Dict[int, bool] = field(default_factory=dict)

    def ensure_token(self, t: int, ready: bool) -> None:
        if t not in self.token_ready:
            self.token_ready[t] = ready

    def set_ready(self, t: int, ready: bool) -> None:
        self.token_ready[t] = ready

    def is_ready(self, t: int) -> bool:
        return self.token_ready.get(t, True)

    def all_ready(self, tokens: List[int]) -> bool:
        return all(self.is_ready(t) for t in tokens)


# -----------------------------
# ROB-lite: commit order only
# -----------------------------
@dataclass
class ROBEntry:
    ins: Instr
    done: bool = False

@dataclass
class ROB:
    capacity: int
    entries: Deque[ROBEntry] = field(default_factory=deque)

    def can_alloc(self) -> bool:
        return len(self.entries) < self.capacity

    def alloc(self, ins: Instr) -> None:
        self.entries.append(ROBEntry(ins=ins, done=False))

    def mark_done(self, iid: int) -> None:
        for e in self.entries:
            if e.ins.iid == iid:
                e.done = True
                return
        raise RuntimeError(f"ROB cannot find iid={iid} to mark done")

    def retire_in_order(self, max_retire: int) -> List[Instr]:
        retired: List[Instr] = []
        for _ in range(max_retire):
            if not self.entries:
                break
            head = self.entries[0]
            if not head.done:
                break
            retired.append(head.ins)
            self.entries.popleft()
        return retired


# -----------------------------
# Queue model
# -----------------------------
@dataclass
class IssueQueue:
    name: str
    capacity: int
    q: Deque[Instr] = field(default_factory=deque)

    def push(self, ins: Instr) -> bool:
        if len(self.q) >= self.capacity:
            return False
        self.q.append(ins)
        return True

    def empty(self) -> bool:
        return not self.q

    def __len__(self) -> int:
        return len(self.q)

    def pick_with_scan_width(self, scan_width: int, scoreboard: Scoreboard) -> Optional[Instr]:
        """
        Scan up to scan_width entries from head.
        scan_width=1 -> only head
        scan_width=4 -> head..head+3
        """
        if not self.q:
            return None
        window = min(len(self.q), scan_width)
        for i in range(window):
            ins = self.q[i]
            if scoreboard.all_ready(ins.reads):
                return ins
        return None

    def pop_specific(self, iid: int) -> Instr:
        for i, x in enumerate(self.q):
            if x.iid == iid:
                del self.q[i]
                return x
        raise RuntimeError(f"{self.name}: iid={iid} not found")


# -----------------------------
# Units
# -----------------------------
@dataclass
class Unit:
    name: str
    latency: int
    busy_until: int = 0
    on_cycles: int = 0

    def is_free(self, cycle: int) -> bool:
        return cycle >= self.busy_until

    def start(self, cycle: int) -> int:
        self.busy_until = cycle + self.latency
        return self.busy_until


# -----------------------------
# MSHR / credits / QoS
# -----------------------------
@dataclass
class MSHR:
    base_entries: int
    gated_entries: int
    in_flight_cpu: int = 0
    in_flight_vec: int = 0

    def total_capacity(self) -> int:
        return self.base_entries + self.gated_entries

    def total_in_flight(self) -> int:
        return self.in_flight_cpu + self.in_flight_vec

    def can_accept_cpu(self) -> bool:
        return self.total_in_flight() < self.total_capacity()

    def can_accept_vec(self, vec_credit_limit: int) -> bool:
        if self.in_flight_vec >= vec_credit_limit:
            return False
        return self.total_in_flight() < self.total_capacity()

    def alloc_cpu(self) -> None:
        self.in_flight_cpu += 1

    def alloc_vec(self) -> None:
        self.in_flight_vec += 1

    def retire_some(self, cpu_retire: int, vec_retire: int) -> None:
        self.in_flight_cpu = max(0, self.in_flight_cpu - cpu_retire)
        self.in_flight_vec = max(0, self.in_flight_vec - vec_retire)


# -----------------------------
# Dispatcher + Queue Classifier
# -----------------------------
@dataclass
class Dispatcher:
    q_int0: IssueQueue
    q_int1: IssueQueue
    q_lsq: IssueQueue
    q_fp: IssueQueue
    q_vec: IssueQueue

    def dispatch(self, ins: Instr) -> Tuple[bool, str]:
        if ins.cls == "INT":
            target = self.q_int0 if (ins.iid % 2 == 0) else self.q_int1
            ok = target.push(ins)
            return ok, "intq_full" if not ok else "ok"

        if ins.cls in ("LD", "ST"):
            ok = self.q_lsq.push(ins)
            return ok, "lsq_full" if not ok else "ok"

        if ins.cls == "FP":
            ok = self.q_fp.push(ins)
            return ok, "fpq_full" if not ok else "ok"

        if ins.cls == "VEC":
            ok = self.q_vec.push(ins)
            return ok, "vecq_full" if not ok else "ok"

        return False, "unknown_cls"


# ============================================================
# Workload generator
# ------------------------------------------------------------
# Versioned token model:
# - architectural register -> current token version
# - writes allocate new token versions
# - reads use current token versions
# This avoids "future writer blocks past reader" bugs.
# ============================================================
@dataclass
class WorkloadConfig:
    seed: int = 42
    num_instr: int = 5000
    num_arch_regs: int = 32
    mem_op_prob: float = 0.25
    fp_prob: float = 0.10
    vec_prob: float = 0.10
    miss_prob_mem: float = 0.25

def gen_workload(cfg: WorkloadConfig) -> Tuple[List[Instr], Scoreboard]:
    rnd = random.Random(cfg.seed)

    sb = Scoreboard()

    # architectural register -> current token version
    arch_map = list(range(cfg.num_arch_regs))
    next_token = cfg.num_arch_regs

    # initial architectural state is ready
    for t in arch_map:
        sb.ensure_token(t, True)

    wl: List[Instr] = []

    for iid in range(cfg.num_instr):
        r = rnd.random()
        if r < (1.0 - (cfg.mem_op_prob + cfg.fp_prob + cfg.vec_prob)):
            cls = "INT"
        elif r < (1.0 - (cfg.fp_prob + cfg.vec_prob)):
            cls = "LD" if rnd.random() < 0.75 else "ST"
        elif r < (1.0 - cfg.vec_prob):
            cls = "FP"
        else:
            cls = "VEC"

        # 0~2 source arch regs
        num_reads = rnd.choice([0, 1, 2])
        read_regs = rnd.sample(range(cfg.num_arch_regs), k=num_reads) if num_reads > 0 else []
        reads = [arch_map[r] for r in read_regs]

        # ~70% chance of 1 destination write
        writes: List[int] = []
        if rnd.random() < 0.70:
            dst_reg = rnd.randrange(cfg.num_arch_regs)
            new_token = next_token
            next_token += 1

            writes = [new_token]
            sb.ensure_token(new_token, False)

            # subsequent instructions now depend on this new version
            arch_map[dst_reg] = new_token

        mem_op = cls in ("LD", "ST")
        mem_miss = mem_op and (rnd.random() < cfg.miss_prob_mem)

        wl.append(
            Instr(
                iid=iid,
                cls=cls,
                reads=reads,
                writes=writes,
                mem_op=mem_op,
                mem_miss=mem_miss,
                age=iid,
            )
        )

    return wl, sb


# ============================================================
# Simulator config/stats
# ============================================================
@dataclass
class SimConfig:
    seed: int = 1234

    scan_width: int = 4
    dispatch_width: int = 3
    retire_width: int = 4

    intq_cap: int = 6
    lsq_cap: int = 8
    fpq_cap: int = 4
    vecq_cap: int = 8

    rob_cap: int = 64

    lat_int: int = 1
    lat_lsu: int = 3
    lat_fp: int = 4
    lat_vec: int = 4

    mshr_base: int = 4
    mshr_gated: int = 4
    vec_credit_limit: int = 3
    lsq_pressure_threshold: int = 6

    retire_cpu_mshr_per_cycle: int = 1
    retire_vec_mshr_per_cycle: int = 1

    vec_stream_prob: float = 0.35
    deadlock_watchdog_cycles: int = 10000

@dataclass
class SimStats:
    cycles: int = 0
    retired: int = 0
    retired_by_cls: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    dispatch_fail: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    stall_reasons: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    unit_on: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    rob_full_cycles: int = 0


# ============================================================
# Simulation
# ============================================================
def simulate(workload: List[Instr], scoreboard: Scoreboard, cfg: SimConfig) -> SimStats:
    rnd = random.Random(cfg.seed)

    q_int0 = IssueQueue("INT0Q", cfg.intq_cap)
    q_int1 = IssueQueue("INT1Q", cfg.intq_cap)
    q_lsq  = IssueQueue("LSQ", cfg.lsq_cap)
    q_fp   = IssueQueue("FPQ", cfg.fpq_cap)
    q_vec  = IssueQueue("VECQ", cfg.vecq_cap)

    disp = Dispatcher(q_int0, q_int1, q_lsq, q_fp, q_vec)

    u_int0 = Unit("INT0", cfg.lat_int)
    u_int1 = Unit("INT1", cfg.lat_int)
    u_lsu  = Unit("LSU", cfg.lat_lsu)
    u_fp   = Unit("FP", cfg.lat_fp)
    u_vec  = Unit("VEC", cfg.lat_vec)

    rob = ROB(cfg.rob_cap)
    mshr = MSHR(cfg.mshr_base, cfg.mshr_gated)

    # iid -> (done_cycle, instr)
    exec_done: Dict[int, Tuple[int, Instr]] = {}

    stats = SimStats()
    cycle = 0
    fetch_idx = 0
    total = len(workload)
    idle_cycles = 0

    def count_on(unit: Unit, driving_queue: IssueQueue) -> None:
        if (not unit.is_free(cycle)) or (len(driving_queue) > 0):
            unit.on_cycles += 1

    def start_exec(unit: Unit, ins: Instr) -> None:
        done = unit.start(cycle)
        exec_done[ins.iid] = (done, ins)

    def try_issue_int(q: IssueQueue, unit: Unit, label: str) -> bool:
        if q.empty():
            return False
        if not unit.is_free(cycle):
            stats.stall_reasons[f"{label}_unit_busy"] += 1
            return False

        ins = q.pick_with_scan_width(cfg.scan_width, scoreboard)
        if ins is None:
            stats.stall_reasons[f"{label}_dep_stall"] += 1
            return False

        q.pop_specific(ins.iid)
        start_exec(unit, ins)
        return True

    def try_issue_lsu() -> bool:
        if q_lsq.empty():
            return False
        if not u_lsu.is_free(cycle):
            stats.stall_reasons["lsu_unit_busy"] += 1
            return False

        ins = q_lsq.pick_with_scan_width(cfg.scan_width, scoreboard)
        if ins is None:
            stats.stall_reasons["lsq_dep_stall"] += 1
            return False

        if ins.mem_miss:
            if not mshr.can_accept_cpu():
                stats.stall_reasons["mshr_full_cpu"] += 1
                return False
            mshr.alloc_cpu()

        q_lsq.pop_specific(ins.iid)
        start_exec(u_lsu, ins)
        return True

    def try_issue_fp() -> bool:
        if q_fp.empty():
            return False
        if not u_fp.is_free(cycle):
            stats.stall_reasons["fp_unit_busy"] += 1
            return False

        ins = q_fp.pick_with_scan_width(cfg.scan_width, scoreboard)
        if ins is None:
            stats.stall_reasons["fp_dep_stall"] += 1
            return False

        q_fp.pop_specific(ins.iid)
        start_exec(u_fp, ins)
        return True

    def try_issue_vec() -> bool:
        if q_vec.empty():
            return False
        if not u_vec.is_free(cycle):
            stats.stall_reasons["vec_unit_busy"] += 1
            return False

        ins = q_vec.pick_with_scan_width(cfg.scan_width, scoreboard)
        if ins is None:
            stats.stall_reasons["vec_dep_stall"] += 1
            return False

        vec_stream_like = (rnd.random() < cfg.vec_stream_prob)
        if vec_stream_like:
            if len(q_lsq) >= cfg.lsq_pressure_threshold:
                stats.stall_reasons["vec_throttled_lsq_pressure"] += 1
                return False
            if not mshr.can_accept_vec(cfg.vec_credit_limit):
                stats.stall_reasons["mshr_or_credit_full_vec"] += 1
                return False
            mshr.alloc_vec()

        q_vec.pop_specific(ins.iid)
        start_exec(u_vec, ins)
        return True

    while stats.retired < total:
        # -----------------------------------------
        # 1) Dispatch + ROB allocation
        # -----------------------------------------
        dispatched_this_cycle = 0
        while dispatched_this_cycle < cfg.dispatch_width and fetch_idx < total:
            if not rob.can_alloc():
                stats.rob_full_cycles += 1
                stats.dispatch_fail["rob_full"] += 1
                break

            ins = workload[fetch_idx]
            ok, reason = disp.dispatch(ins)
            if not ok:
                stats.dispatch_fail[reason] += 1
                break

            rob.alloc(ins)
            fetch_idx += 1
            dispatched_this_cycle += 1

        # -----------------------------------------
        # 2) Rough power proxy
        # -----------------------------------------
        count_on(u_int0, q_int0)
        count_on(u_int1, q_int1)
        count_on(u_lsu, q_lsq)
        count_on(u_fp, q_fp)
        count_on(u_vec, q_vec)

        # -----------------------------------------
        # 3) Issue
        # CPU LSU first for QoS
        # -----------------------------------------
        issued_any = False
        issued_any |= try_issue_int(q_int0, u_int0, "int0")
        issued_any |= try_issue_int(q_int1, u_int1, "int1")
        issued_any |= try_issue_lsu()
        issued_any |= try_issue_fp()
        issued_any |= try_issue_vec()

        if not issued_any:
            stats.stall_reasons["global_no_issue"] += 1

        # -----------------------------------------
        # 4) Writeback (next cycle after completion)
        # -----------------------------------------
        done_iids = [iid for iid, (dc, _) in exec_done.items() if dc < cycle]
        for iid in done_iids:
            _, ins = exec_done.pop(iid)
            for t in ins.writes:
                scoreboard.set_ready(t, True)
            rob.mark_done(iid)

        # -----------------------------------------
        # 5) In-order retire
        # -----------------------------------------
        retired_now = rob.retire_in_order(cfg.retire_width)
        for ins in retired_now:
            stats.retired += 1
            stats.retired_by_cls[ins.cls] += 1

        # -----------------------------------------
        # 6) MSHR completion (toy)
        # -----------------------------------------
        mshr.retire_some(cfg.retire_cpu_mshr_per_cycle, cfg.retire_vec_mshr_per_cycle)

        # -----------------------------------------
        # 7) Progress watchdog
        # -----------------------------------------
        progress = False
        if dispatched_this_cycle > 0:
            progress = True
        if issued_any:
            progress = True
        if done_iids:
            progress = True
        if retired_now:
            progress = True

        if progress:
            idle_cycles = 0
        else:
            idle_cycles += 1

        if idle_cycles > cfg.deadlock_watchdog_cycles:
            print("\n[DEBUG] No forward progress detected")
            print(f"cycle={cycle}")
            print(f"fetch_idx={fetch_idx}/{total}")
            print(f"ROB size={len(rob.entries)}")
            if rob.entries:
                head = rob.entries[0]
                print(f"ROB head: iid={head.ins.iid}, done={head.done}, cls={head.ins.cls}")

            print(f"INT0Q={len(q_int0)}, INT1Q={len(q_int1)}, LSQ={len(q_lsq)}, FPQ={len(q_fp)}, VECQ={len(q_vec)}")
            if len(q_int0): print("INT0Q head:", q_int0.q[0])
            if len(q_int1): print("INT1Q head:", q_int1.q[0])
            if len(q_lsq): print("LSQ head:", q_lsq.q[0])
            if len(q_fp): print("FPQ head:", q_fp.q[0])
            if len(q_vec): print("VECQ head:", q_vec.q[0])

            print(f"MSHR cpu={mshr.in_flight_cpu}, vec={mshr.in_flight_vec}, total={mshr.total_in_flight()}/{mshr.total_capacity()}")
            raise RuntimeError("No forward progress detected")

        # -----------------------------------------
        # 8) Invariants
        # -----------------------------------------
        assert len(q_int0) <= q_int0.capacity
        assert len(q_int1) <= q_int1.capacity
        assert len(q_lsq) <= q_lsq.capacity
        assert len(q_fp) <= q_fp.capacity
        assert len(q_vec) <= q_vec.capacity
        assert len(rob.entries) <= rob.capacity
        assert mshr.total_in_flight() <= mshr.total_capacity()

        cycle += 1
        stats.cycles = cycle

        if cycle > 5_000_000:
            raise RuntimeError(
                "Simulation runaway > 5,000,000 cycles. "
                "This usually indicates either a true deadlock or a modeling bug."
            )

    stats.unit_on["INT0"] = u_int0.on_cycles
    stats.unit_on["INT1"] = u_int1.on_cycles
    stats.unit_on["LSU"] = u_lsu.on_cycles
    stats.unit_on["FP"] = u_fp.on_cycles
    stats.unit_on["VEC"] = u_vec.on_cycles

    return stats


# ============================================================
# Pretty print
# ============================================================
def pretty_print(stats: SimStats) -> None:
    ipc = stats.retired / stats.cycles if stats.cycles else 0.0
    print(f"Cycles:   {stats.cycles}")
    print(f"Retired:  {stats.retired}")
    print(f"IPC:      {ipc:.3f}")
    print()

    print("Retired by class:")
    for k in sorted(stats.retired_by_cls.keys()):
        print(f"  {k:4s}: {stats.retired_by_cls[k]}")
    print()

    print("Dispatch fail reasons (backpressure):")
    for k, v in sorted(stats.dispatch_fail.items(), key=lambda x: -x[1]):
        print(f"  {k:18s}: {v}")
    print()

    print("Stall reasons:")
    for k, v in sorted(stats.stall_reasons.items(), key=lambda x: -x[1]):
        print(f"  {k:24s}: {v}")
    print()

    print("Unit ON cycles (rough power proxy):")
    for k, v in stats.unit_on.items():
        print(f"  {k:4s}: {v} ({v / stats.cycles:.2%})")
    print()

    if stats.rob_full_cycles:
        print(f"ROB full cycles: {stats.rob_full_cycles} ({stats.rob_full_cycles / stats.cycles:.2%})")


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    wcfg = WorkloadConfig(
        seed=42,
        num_instr=5000,
        num_arch_regs=32,
        mem_op_prob=0.25,
        fp_prob=0.10,
        vec_prob=0.10,
        miss_prob_mem=0.25,
    )
    wl, sb = gen_workload(wcfg)

    scfg = SimConfig(
        seed=1234,
        scan_width=4,
        dispatch_width=3,
        retire_width=4,
        intq_cap=6,
        lsq_cap=8,
        fpq_cap=4,
        vecq_cap=8,
        rob_cap=64,
        lat_int=1,
        lat_lsu=3,
        lat_fp=4,
        lat_vec=4,
        mshr_base=4,
        mshr_gated=4,
        vec_credit_limit=3,
        lsq_pressure_threshold=6,
        retire_cpu_mshr_per_cycle=1,
        retire_vec_mshr_per_cycle=1,
        vec_stream_prob=0.35,
        deadlock_watchdog_cycles=10000,
    )

    st = simulate(wl, sb, scfg)
    print("=== CONFIG ===")
    print(scfg)
    print("==============")
    pretty_print(st)
