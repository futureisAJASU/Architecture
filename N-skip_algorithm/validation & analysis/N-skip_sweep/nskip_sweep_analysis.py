import random
import csv
import math
from collections import deque, Counter, defaultdict

# =========================================================
# Multi-cycle N-skip simulator (Method B)
# =========================================================

def sample_state(prev_state, stickiness, p_ready, p_miss):
    """
    State:
      0 = ready immediately
      1 = short latency
      2 = long latency (miss-like)
    """
    def fresh_state():
        if random.random() < p_miss:
            return 2
        return 0 if random.random() < p_ready else 1

    if prev_state is None:
        return fresh_state()

    if random.random() < stickiness:
        return prev_state
    return fresh_state()


def latency_from_state(state, short_lat_range, long_lat_range):
    if state == 0:
        return 0
    elif state == 1:
        return random.randint(*short_lat_range)
    else:
        return random.randint(*long_lat_range)


def run_one_sim(
    N: int,
    cycles: int,
    warmup: int,
    queue_len: int,
    p_ready: float,
    stickiness: float,
    p_miss: float,
    short_lat_range,
    long_lat_range,
    power_scan_unit: float,
    power_issue_op: float,
    power_leakage: float,
):
    """
    Multi-cycle simulation:
      - persistent queue with ready_time per entry
      - scan up to N+1 from head, early-out, issue at most 1 per cycle
      - issued entry removed, new entry appended
    Returns:
      issue_rate, avg_power, perf_per_watt
    """

    q = deque()
    prev_state = None

    # Init queue at t=0
    t = 0
    for _ in range(queue_len):
        prev_state = sample_state(prev_state, stickiness, p_ready, p_miss)
        lat = latency_from_state(prev_state, short_lat_range, long_lat_range)
        q.append(t + lat)

    issued_count = 0
    total_power = 0.0

    for t in range(cycles):
        cycle_power = power_leakage
        issued = 0

        scan_len = min(queue_len, N + 1)
        ready_idx = None

        # Scan head..N
        for i in range(scan_len):
            cycle_power += power_scan_unit
            if t >= q[i]:
                ready_idx = i
                break

        if ready_idx is not None:
            cycle_power += power_issue_op
            issued = 1

            # Remove issued entry at index ready_idx (queue_len small -> list ok)
            tmp = list(q)
            tmp.pop(ready_idx)
            q = deque(tmp)

            # Refill
            prev_state = sample_state(prev_state, stickiness, p_ready, p_miss)
            lat = latency_from_state(prev_state, short_lat_range, long_lat_range)
            q.append(t + lat)

        total_power += cycle_power

        if t >= warmup:
            issued_count += issued

    measured_cycles = cycles - warmup
    issue_rate = issued_count / measured_cycles
    avg_power = total_power / cycles
    perf_per_watt = issue_rate / avg_power
    return issue_rate, avg_power, perf_per_watt


# =========================================================
# Utility: stats helpers
# =========================================================

def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")

def stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)

def topk_includes(n, scores_by_n, k=2):
    # returns True if n is in top-k N values by score
    items = sorted(scores_by_n.items(), key=lambda kv: kv[1], reverse=True)
    top = [kv[0] for kv in items[:k]]
    return n in top


# =========================================================
# A + B runner
# =========================================================

def run_A_and_B():
    # -----------------------------
    # Core energy model (relative)
    # -----------------------------
    POWER_SCAN_UNIT = 1.0
    POWER_ISSUE_OP  = 8.0
    POWER_LEAKAGE   = 5.0

    # -----------------------------
    # Architecture / model params
    # -----------------------------
    queue_len = 16
    N_max = 8

    short_lat_range = (1, 4)
    long_lat_range  = (12, 40)

    # -----------------------------
    # Monte Carlo controls
    # -----------------------------
    # Tip: B sweep is expensive. Start smaller, then crank up.
    cycles = 20000
    warmup = 2000
    seeds  = list(range(10))   # A: seed repetitions
    p_list = [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8]

    # -----------------------------
    # B sweep grid
    # -----------------------------
    stickiness_list = [0.60, 0.70, 0.80, 0.85, 0.90, 0.95]
    p_miss_list     = [0.05, 0.10, 0.15, 0.20]

    # Output files
    out_A_csv = "A_seed_summary.csv"
    out_B_csv = "B_sweep_summary.csv"

    # =====================================================
    # (A) Seed repetitions at a single (stickiness, p_miss)
    # =====================================================
    base_stickiness = 0.85
    base_p_miss = 0.10

    # Store A results
    # A_data[p][N] -> list of perf/watt across seeds
    A_ppw = {p: {N: [] for N in range(N_max+1)} for p in p_list}
    A_issue = {p: {N: [] for N in range(N_max+1)} for p in p_list}
    A_power = {p: {N: [] for N in range(N_max+1)} for p in p_list}

    # best-N counts and top-k hits (for N=4)
    A_bestN_counts = {p: Counter() for p in p_list}
    A_top2_hit_N4 = {p: 0 for p in p_list}  # how many seeds N=4 in top2
    A_top1_hit_N4 = {p: 0 for p in p_list}  # how many seeds N=4 best

    print("Running (A) seed repetitions...")
    for p in p_list:
        for seed in seeds:
            random.seed(seed)

            scores_seed = {}
            for N in range(N_max+1):
                ir, pw, ppw = run_one_sim(
                    N=N,
                    cycles=cycles,
                    warmup=warmup,
                    queue_len=queue_len,
                    p_ready=p,
                    stickiness=base_stickiness,
                    p_miss=base_p_miss,
                    short_lat_range=short_lat_range,
                    long_lat_range=long_lat_range,
                    power_scan_unit=POWER_SCAN_UNIT,
                    power_issue_op=POWER_ISSUE_OP,
                    power_leakage=POWER_LEAKAGE,
                )
                A_ppw[p][N].append(ppw)
                A_issue[p][N].append(ir)
                A_power[p][N].append(pw)
                scores_seed[N] = ppw

            # best N for this seed
            bestN = max(scores_seed.items(), key=lambda kv: kv[1])[0]
            A_bestN_counts[p][bestN] += 1

            # top-1 / top-2 hit of N=4
            if bestN == 4:
                A_top1_hit_N4[p] += 1
            if topk_includes(4, scores_seed, k=2):
                A_top2_hit_N4[p] += 1

        # quick console summary
        most_common = A_bestN_counts[p].most_common(3)
        print(f"  p={p}: bestN top3 = {most_common}, N=4 top1 {A_top1_hit_N4[p]}/{len(seeds)}, top2 {A_top2_hit_N4[p]}/{len(seeds)}")

    # Write A summary CSV
    with open(out_A_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "p_ready","N",
            "ppw_mean","ppw_stdev",
            "issue_mean","power_mean",
            "bestN_count_at_p",  # how often THIS N was best (across seeds)
            "N4_top1_hits","N4_top2_hits","num_seeds",
            "base_stickiness","base_p_miss",
            "cycles","warmup","queue_len",
            "POWER_SCAN_UNIT","POWER_ISSUE_OP","POWER_LEAKAGE",
        ])

        for p in p_list:
            for N in range(N_max+1):
                w.writerow([
                    p, N,
                    mean(A_ppw[p][N]), stdev(A_ppw[p][N]),
                    mean(A_issue[p][N]), mean(A_power[p][N]),
                    A_bestN_counts[p][N],
                    A_top1_hit_N4[p], A_top2_hit_N4[p], len(seeds),
                    base_stickiness, base_p_miss,
                    cycles, warmup, queue_len,
                    POWER_SCAN_UNIT, POWER_ISSUE_OP, POWER_LEAKAGE,
                ])

    print(f"(A) wrote: {out_A_csv}")

    # =====================================================
    # (B) Sweep stickiness x p_miss (per p_ready)
    # For each grid point, compute:
    #  - bestN (by mean ppw over seeds)
    #  - best_ppw_mean
    #  - ppw_mean_at_N4
    #  - regret_N4 = best_ppw_mean - ppw_mean_at_N4
    # =====================================================

    print("Running (B) parameter sweep...")
    with open(out_B_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "p_ready","stickiness","p_miss",
            "bestN","best_ppw_mean",
            "ppw_mean_N4","regret_N4",
            "ppw_mean_N0","ppw_mean_N2","ppw_mean_N4_alt","ppw_mean_N6","ppw_mean_N8",
            "num_seeds",
            "cycles","warmup","queue_len",
            "short_lat_min","short_lat_max","long_lat_min","long_lat_max",
            "POWER_SCAN_UNIT","POWER_ISSUE_OP","POWER_LEAKAGE",
        ])

        for p in p_list:
            for stick in stickiness_list:
                for pm in p_miss_list:
                    # compute mean ppw for each N across seeds
                    ppw_mean_by_N = {}
                    for N in range(N_max+1):
                        vals = []
                        for seed in seeds:
                            random.seed(seed)
                            _, _, ppw = run_one_sim(
                                N=N,
                                cycles=cycles,
                                warmup=warmup,
                                queue_len=queue_len,
                                p_ready=p,
                                stickiness=stick,
                                p_miss=pm,
                                short_lat_range=short_lat_range,
                                long_lat_range=long_lat_range,
                                power_scan_unit=POWER_SCAN_UNIT,
                                power_issue_op=POWER_ISSUE_OP,
                                power_leakage=POWER_LEAKAGE,
                            )
                            vals.append(ppw)
                        ppw_mean_by_N[N] = mean(vals)

                    bestN = max(ppw_mean_by_N.items(), key=lambda kv: kv[1])[0]
                    best_ppw = ppw_mean_by_N[bestN]
                    ppw_N4 = ppw_mean_by_N[4]
                    regret = best_ppw - ppw_N4

                    # extra columns for quick comparison snapshots
                    w.writerow([
                        p, stick, pm,
                        bestN, best_ppw,
                        ppw_N4, regret,
                        ppw_mean_by_N[0], ppw_mean_by_N[2], ppw_N4, ppw_mean_by_N[6], ppw_mean_by_N[8],
                        len(seeds),
                        cycles, warmup, queue_len,
                        short_lat_range[0], short_lat_range[1], long_lat_range[0], long_lat_range[1],
                        POWER_SCAN_UNIT, POWER_ISSUE_OP, POWER_LEAKAGE,
                    ])

            print(f"  done p={p}")

    print(f"(B) wrote: {out_B_csv}")
    print("All done.")


if __name__ == "__main__":
    run_A_and_B()
