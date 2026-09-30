"""Order intent lifecycle (borrowed from jev-trader's status machine).

jev-trader lesson: a quote is an INTENT first, and the truth arrives later.
    sent -> placed | reverted | lost   (live)
    sim  -> filled                     (paper)

Our paper loop marks orders "sim" and fills immediately; when real execution
lands (phase 2) the same records carry the receipt lifecycle, so logs and
counters never have to change shape.
"""

STATUS_INTENT = "intent"   # built by the strategy, not yet sent
STATUS_SENT = "sent"       # submitted, receipt pending
STATUS_PLACED = "placed"   # exchange acknowledged (order id known)
STATUS_REVERTED = "reverted"  # rejected / book moved through our price
STATUS_LOST = "lost"       # no receipt within N cycles
STATUS_SIM = "sim"         # paper mode: simulated fill
STATUS_FILLED = "filled"   # real fill observed

LIVE_TERMINAL = {STATUS_PLACED, STATUS_REVERTED, STATUS_LOST}
PAPER_TERMINAL = {STATUS_SIM}


def new_intent(order, seq):
    """Wrap a strategy order dict into an intent record (never mutates input)."""
    rec = dict(order)
    rec["seq"] = seq
    rec["status"] = STATUS_INTENT
    rec["order_id"] = None
    rec["receipt_cycles"] = 0
    return rec


def mark_sent(rec):
    rec["status"] = STATUS_SENT
    return rec


def mark_placed(rec, order_id):
    rec["status"] = STATUS_PLACED
    rec["order_id"] = order_id
    return rec


def mark_reverted(rec, reason=""):
    rec["status"] = STATUS_REVERTED
    rec["revert_reason"] = reason
    return rec


def mark_lost(rec):
    rec["status"] = STATUS_LOST
    return rec


def mark_sim_filled(rec):
    rec["status"] = STATUS_SIM
    return rec


def age_pending(records, max_cycles=10):
    """Advance receipt-less records; age them out to 'lost' after max_cycles.

    Mirrors jev-trader: 'No receipt after 10 blocks gives lost.'
    """
    for rec in records:
        if rec.get("status") == STATUS_SENT:
            rec["receipt_cycles"] = rec.get("receipt_cycles", 0) + 1
            if rec["receipt_cycles"] >= max_cycles:
                mark_lost(rec)
    return records
