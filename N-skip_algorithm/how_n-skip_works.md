##  N-Skip Issue Policy: How it Works

The core idea is to efficiently find a ready instruction in the issue queue 
while minimizing scan power. Instead of checking every single entry, 
we limit the search range to `N+1` entries and implement an `early-out` mechanism.

Imagine an Instruction Queue (IQ) where '1' means ready and '0' means not ready:

[0, 1, 0, 0, 1, 0, 0, 0, ...] ^ Head of Queue

Key Advantages:

Power Savings: Early-out significantly reduces unnecessary scan power.

Improved Issue rate (over In-Order): Finds ready instructions faster than strict in-order.

Bounded Complexity: Limits the hardware complexity for low-power cores.  

----------------------------------
  
Here's the simplified logic:

```python
current_power_cost = BASELINE_POWER

# Iterate up to N+1 entries from the queue head
for i in range(min(len(queue), N_SKIP_RANGE + 1)):
    current_power_cost += SCAN_UNIT_POWER  # Cost for checking an entry

    if queue[i] == 1:                     # Is this instruction ready?
        current_power_cost += ISSUE_OP_POWER # Yes! Pay issue cost.
        ISSUE_INSTRUCTION()               # Issue it to execution unit.
        break                             # EARLY-OUT! Stop scanning immediately.
    # else: Continue to the next entry if not ready
