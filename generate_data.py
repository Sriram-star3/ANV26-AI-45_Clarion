"""Data generator for Clarion incident scenarios.

Generates realistic telemetry, ledger, fleet events, support tickets, and audit logs
for the festival_deadlock and gateway_outage scenarios.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def generate_scenario(scenario: str = "festival_deadlock", seed: int = 42, out_dir: str | Path = "data") -> dict[str, int]:
    """Generate deterministic incident data files for Clarion."""
    rng = np.random.default_rng(seed)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Timeframe: 18:00 - 21:30 IST on 2026-10-07 (211 minutes inclusive)
    start_dt = pd.Timestamp("2026-10-07 18:00:00")
    end_dt = pd.Timestamp("2026-10-07 21:30:00")
    minutes = pd.date_range(start_dt, end_dt, freq="1min")
    n_minutes = len(minutes)

    # -------------------------------------------------------------
    # 1. Telemetry Data
    # -------------------------------------------------------------
    # Metrics per minute
    orders_placed = rng.integers(42, 49, size=n_minutes)

    # Base signals
    completion_rate = np.zeros(n_minutes)
    db_lock_waits = np.zeros(n_minutes)
    alloc_latency_sec = np.zeros(n_minutes)
    payment_502_count = np.zeros(n_minutes)
    gateway_p95_ms = np.zeros(n_minutes)
    rider_rejection_rate = np.zeros(n_minutes)
    dispatch_queue_depth = np.zeros(n_minutes)

    for i, t in enumerate(minutes):
        minute_str = t.strftime("%H:%M")

        # Baseline conditions (18:00 to ~18:44)
        base_completion = 0.947 + rng.normal(0, 0.003)
        base_locks = max(1, int(round(3.0 + rng.normal(0, 1.5))))
        base_latency = max(0.8, round(1.2 + rng.normal(0, 0.35), 2))
        # Keep base 502 count low with small std so sigma jump is the highest among all alerting metrics
        base_502 = max(1, int(round(2.0 + rng.normal(0, 0.35))))
        base_p95 = max(90, int(round(120 + rng.normal(0, 8))))
        base_rejection = max(0.06, round(0.08 + rng.normal(0, 0.005), 4))
        base_queue = max(2, int(round(5 + rng.normal(0, 1.5))))

        if scenario == "festival_deadlock":
            # 18:48: DB lock spike and allocation latency spike
            if minute_str < "18:48":
                db_lock_waits[i] = base_locks
                alloc_latency_sec[i] = base_latency
            else:
                db_lock_waits[i] = int(round(180 + rng.normal(0, 10)))
                alloc_latency_sec[i] = round(42.0 + rng.normal(0, 2.5), 2)

            # 18:49: Completion rate drops from ~94.7% to ~67.8% (drop ~28.4%)
            if minute_str < "18:49":
                completion_rate[i] = base_completion
                dispatch_queue_depth[i] = base_queue
            else:
                completion_rate[i] = max(0.64, min(0.71, 0.678 + rng.normal(0, 0.008)))
                dispatch_queue_depth[i] = int(round(68 + rng.normal(0, 5)))

            # 18:50: payment_502_count surge
            if minute_str < "18:50":
                payment_502_count[i] = base_502
                gateway_p95_ms[i] = base_p95
            else:
                payment_502_count[i] = int(round(90 + rng.normal(0, 5)))
                gateway_p95_ms[i] = int(round(850 + rng.normal(0, 30)))

            # 19:05: Rain ramp elevates rider rejection rate
            if minute_str < "19:05":
                rider_rejection_rate[i] = base_rejection
            else:
                rider_rejection_rate[i] = max(0.25, min(0.35, 0.30 + rng.normal(0, 0.012)))

        else:  # gateway_outage
            db_lock_waits[i] = base_locks
            alloc_latency_sec[i] = base_latency
            rider_rejection_rate[i] = base_rejection
            dispatch_queue_depth[i] = base_queue

            # 18:47: payment 502 surge
            if minute_str < "18:47":
                payment_502_count[i] = base_502
                gateway_p95_ms[i] = base_p95
            else:
                payment_502_count[i] = int(round(88 + rng.normal(0, 5)))
                gateway_p95_ms[i] = int(round(920 + rng.normal(0, 25)))

            # 18:49: completion rate drop ~25%
            if minute_str < "18:49":
                completion_rate[i] = base_completion
            else:
                completion_rate[i] = max(0.68, min(0.74, 0.710 + rng.normal(0, 0.007)))

    telemetry_df = pd.DataFrame({
        "ts": [t.strftime("%Y-%m-%d %H:%M:%S") for t in minutes],
        "orders_placed": orders_placed,
        "completion_rate": np.round(completion_rate, 4),
        "db_lock_waits": db_lock_waits.astype(int),
        "alloc_latency_sec": np.round(alloc_latency_sec, 2),
        "payment_502_count": payment_502_count.astype(int),
        "gateway_p95_ms": gateway_p95_ms.astype(int),
        "rider_rejection_rate": np.round(rider_rejection_rate, 4),
        "dispatch_queue_depth": dispatch_queue_depth.astype(int),
    })
    telemetry_df.to_csv(out_path / "telemetry.csv", index=False)

    # -------------------------------------------------------------
    # 2. Payment Ledger Data (~45 orders / min => ~9,450 orders)
    # -------------------------------------------------------------
    ledger_records = []
    order_counter = 1

    for i, t in enumerate(minutes):
        minute_str = t.strftime("%H:%M")
        n_orders = int(orders_placed[i])
        current_comp_rate = float(completion_rate[i])

        for _ in range(n_orders):
            order_id = f"ORD-20261007-{order_counter:05d}"
            order_counter += 1
            sec_offset = int(rng.integers(0, 60))
            order_ts = t + pd.Timedelta(seconds=sec_offset)

            is_completed = rng.random() < current_comp_rate

            if scenario == "festival_deadlock":
                if is_completed:
                    order_status = "COMPLETED"
                    cancel_reason = ""
                    payment_captured = True
                    batch_size = int(rng.choice([1, 2])) if minute_str < "18:48" else int(rng.choice([1, 2, 5]))
                    cancelled_at = ""
                    poll_502_ts = ""
                else:
                    order_status = "CANCELLED"
                    cancel_delay = int(rng.integers(40, 180))
                    c_dt = order_ts + pd.Timedelta(seconds=cancel_delay)
                    cancelled_at = c_dt.strftime("%Y-%m-%d %H:%M:%S")

                    if minute_str < "18:49":
                        # baseline failure distribution: ~1.6% of all orders fail with PAYMENT_FAILED
                        r_choice = rng.random()
                        if r_choice < 0.30:  # ~1.6% of total
                            cancel_reason = "PAYMENT_FAILED"
                            payment_captured = False
                        elif r_choice < 0.70:
                            cancel_reason = "DISPATCH_TIMEOUT"
                            payment_captured = True
                        elif r_choice < 0.90:
                            cancel_reason = "RIDER_REJECTION"
                            payment_captured = True
                        else:
                            cancel_reason = "STOCKOUT"
                            payment_captured = True
                        batch_size = int(rng.choice([1, 2]))
                        poll_502_ts = ""
                    else:
                        # Incident failure distribution:
                        # ~85% DISPATCH_TIMEOUT, ~12% RIDER_REJECTION, ~1.6% total orders PAYMENT_FAILED (approx 5% of failures)
                        r_choice = rng.random()
                        if r_choice < 0.050:  # ~1.6% of total orders
                            cancel_reason = "PAYMENT_FAILED"
                            payment_captured = False
                        elif r_choice < 0.880:  # ~83% of failures
                            cancel_reason = "DISPATCH_TIMEOUT"
                            payment_captured = True
                        elif r_choice < 0.985:  # ~10.5% of failures
                            cancel_reason = "RIDER_REJECTION"
                            payment_captured = True
                        else:
                            cancel_reason = "STOCKOUT"
                            payment_captured = True

                        # Batch size reflects deadlock batching
                        batch_size = int(rng.choice([5, 6])) if cancel_reason == "DISPATCH_TIMEOUT" else int(rng.choice([1, 2]))

                        # 502 polls in festival_deadlock: polling client gets 502 AFTER cancellation
                        if rng.random() < 0.65:
                            p_dt = c_dt + pd.Timedelta(seconds=int(rng.integers(12, 55)))
                            poll_502_ts = p_dt.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            poll_502_ts = ""

            else:  # gateway_outage
                if minute_str < "18:49":
                    if is_completed:
                        order_status = "COMPLETED"
                        cancel_reason = ""
                        payment_captured = True
                        batch_size = int(rng.choice([1, 2]))
                        cancelled_at = ""
                        poll_502_ts = ""
                    else:
                        order_status = "CANCELLED"
                        cancel_delay = int(rng.integers(40, 180))
                        c_dt = order_ts + pd.Timedelta(seconds=cancel_delay)
                        cancelled_at = c_dt.strftime("%Y-%m-%d %H:%M:%S")
                        r_choice = rng.random()
                        if r_choice < 0.30:
                            cancel_reason = "PAYMENT_FAILED"
                            payment_captured = False
                        elif r_choice < 0.70:
                            cancel_reason = "DISPATCH_TIMEOUT"
                            payment_captured = True
                        else:
                            cancel_reason = "RIDER_REJECTION"
                            payment_captured = True
                        batch_size = int(rng.choice([1, 2]))
                        poll_502_ts = ""
                else:
                    # In gateway outage incident: UPI capture drops to ~60%
                    if is_completed:
                        order_status = "COMPLETED"
                        cancel_reason = ""
                        # In gateway outage, capture success falls to ~60% overall
                        payment_captured = rng.random() < 0.845
                        batch_size = int(rng.choice([1, 2]))
                        cancelled_at = ""
                        poll_502_ts = ""
                    else:
                        order_status = "CANCELLED"
                        cancel_delay = int(rng.integers(30, 90))
                        c_dt = order_ts + pd.Timedelta(seconds=cancel_delay)
                        cancelled_at = c_dt.strftime("%Y-%m-%d %H:%M:%S")

                        # In gateway outage: most failures are PAYMENT_FAILED, payment NOT captured
                        r_choice = rng.random()
                        if r_choice < 0.88:
                            cancel_reason = "PAYMENT_FAILED"
                            payment_captured = False
                        elif r_choice < 0.95:
                            cancel_reason = "DISPATCH_TIMEOUT"
                            payment_captured = True
                        else:
                            cancel_reason = "RIDER_REJECTION"
                            payment_captured = True
                        batch_size = int(rng.choice([1, 2]))

                        # In gateway outage: 502 polls occur BEFORE checkout cancellation
                        if rng.random() < 0.70:
                            p_dt = c_dt - pd.Timedelta(seconds=int(rng.integers(10, 25)))
                            poll_502_ts = p_dt.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            poll_502_ts = ""

            ledger_records.append({
                "order_id": order_id,
                "ts": order_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "payment_captured": payment_captured,
                "order_status": order_status,
                "cancel_reason": cancel_reason,
                "batch_size": batch_size,
                "checkout_cancelled_at": cancelled_at,
                "poll_502_ts": poll_502_ts,
            })

    ledger_df = pd.DataFrame(ledger_records)
    ledger_df.to_csv(out_path / "payment_ledger.csv", index=False)

    # -------------------------------------------------------------
    # 3. Fleet Events Data
    # -------------------------------------------------------------
    fleet_records = []
    picker_ids = [f"PKR-{idx:03d}" for idx in range(1, 35)]
    rider_ids = [f"RDR-{idx:03d}" for idx in range(1, 60)]

    for t in minutes:
        minute_str = t.strftime("%H:%M")

        # Regular rider checkins and pick completes
        n_checkins = int(rng.integers(1, 4))
        for _ in range(n_checkins):
            fleet_records.append({
                "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                "event": "RIDER_CHECKIN",
                "entity": str(rng.choice(rider_ids)),
                "value": 1,
            })

        n_picks = int(rng.integers(8, 16))
        for _ in range(n_picks):
            fleet_records.append({
                "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                "event": "PICK_COMPLETE",
                "entity": str(rng.choice(picker_ids)),
                "value": 1,
            })

        if scenario == "festival_deadlock":
            # Pickers idle spike starting 18:48
            if minute_str >= "18:48":
                n_idle = int(rng.integers(4, 9))
                for _ in range(n_idle):
                    fleet_records.append({
                        "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                        "event": "PICKER_IDLE",
                        "entity": str(rng.choice(picker_ids)),
                        "value": int(rng.integers(3, 7)),
                    })
            else:
                if rng.random() < 0.2:
                    fleet_records.append({
                        "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                        "event": "PICKER_IDLE",
                        "entity": str(rng.choice(picker_ids)),
                        "value": 1,
                    })

            # Rider reject spike after rain ramp 19:05
            if minute_str >= "19:05":
                n_rej = int(rng.integers(3, 8))
                for _ in range(n_rej):
                    fleet_records.append({
                        "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                        "event": "RIDER_REJECT",
                        "entity": str(rng.choice(rider_ids)),
                        "value": 1,
                    })
            else:
                if rng.random() < 0.25:
                    fleet_records.append({
                        "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                        "event": "RIDER_REJECT",
                        "entity": str(rng.choice(rider_ids)),
                        "value": 1,
                    })
        else:  # gateway_outage
            if rng.random() < 0.2:
                fleet_records.append({
                    "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                    "event": "PICKER_IDLE",
                    "entity": str(rng.choice(picker_ids)),
                    "value": 1,
                })
            if rng.random() < 0.25:
                fleet_records.append({
                    "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                    "event": "RIDER_REJECT",
                    "entity": str(rng.choice(rider_ids)),
                    "value": 1,
                })

    fleet_df = pd.DataFrame(fleet_records).sort_values("ts").reset_index(drop=True)
    fleet_df.to_csv(out_path / "fleet_events.csv", index=False)

    # -------------------------------------------------------------
    # 4. Support Tickets Data
    # -------------------------------------------------------------
    ticket_records = []
    ticket_counter = 1001

    generic_texts = [
        "Need to change delivery location address",
        "Add extra carry bag to my current order",
        "How do I apply the Diwali discount voucher?",
        "App interface is slightly sluggish today",
        "Delivery partner details missing on tracking page",
    ]
    payment_texts = [
        "Payment debited but order failed immediately",
        "UPI amount deducted from HDFC account but order not placed",
        "502 error during checkout payment confirmation",
        "Bank sent debit SMS but app shows transaction pending/failed",
        "Payment gateway Alpha timed out after UPI PIN",
    ]
    weather_texts = [
        "Heavy rain and waterlogging near Koramangala 4th block",
        "Delivery partner not moving due to thunderstorm and waterlogged roads",
        "Severe water logging outside apartment gate, rider unable to reach",
        "Rain delay reported by delivery partner",
    ]
    warehouse_texts = [
        "Order stuck in packing state for 25 minutes",
        "Items being picked for over 30 mins, dispatch delayed",
        "Darkstore packing status not updating",
    ]

    for t in minutes:
        minute_str = t.strftime("%H:%M")

        # Baseline generic tickets
        if rng.random() < 0.4:
            ticket_records.append({
                "ticket_id": f"TCK-{ticket_counter}",
                "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                "channel": str(rng.choice(["APP_CHAT", "IN_APP_HELP", "WHATSAPP"])),
                "text": str(rng.choice(generic_texts)),
            })
            ticket_counter += 1

        if scenario == "festival_deadlock":
            # Payment tickets appear after 18:50 (client 502 symptom)
            if minute_str >= "18:50" and rng.random() < 0.45:
                ticket_records.append({
                    "ticket_id": f"TCK-{ticket_counter}",
                    "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                    "channel": "APP_CHAT",
                    "text": str(rng.choice(payment_texts)),
                })
                ticket_counter += 1

            # Warehouse delay tickets after 18:48
            if minute_str >= "18:48" and rng.random() < 0.35:
                ticket_records.append({
                    "ticket_id": f"TCK-{ticket_counter}",
                    "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                    "channel": "IN_APP_HELP",
                    "text": str(rng.choice(warehouse_texts)),
                })
                ticket_counter += 1

            # Weather complaints ramp up after 19:05
            if minute_str >= "19:05" and rng.random() < 0.50:
                ticket_records.append({
                    "ticket_id": f"TCK-{ticket_counter}",
                    "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                    "channel": "APP_CHAT",
                    "text": str(rng.choice(weather_texts)),
                })
                ticket_counter += 1

        else:  # gateway_outage
            # Heavy payment tickets after 18:47
            if minute_str >= "18:47" and rng.random() < 0.85:
                ticket_records.append({
                    "ticket_id": f"TCK-{ticket_counter}",
                    "ts": (t + pd.Timedelta(seconds=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
                    "channel": "APP_CHAT",
                    "text": str(rng.choice(payment_texts)),
                })
                ticket_counter += 1

    tickets_df = pd.DataFrame(ticket_records).sort_values("ts").reset_index(drop=True)
    tickets_df.to_csv(out_path / "support_tickets.csv", index=False)

    # -------------------------------------------------------------
    # 5. Audit Log Data
    # -------------------------------------------------------------
    audit_records = [
        # 18:20: Decoy feature flag in both scenarios
        {
            "ts": "2026-10-07 18:20:00",
            "kind": "CONFIG_TOGGLE",
            "key": "search_ranking_v3",
            "old": "false",
            "new": "true",
            "actor": "ml-deployer-svc",
            "scope": "darkstore-blr-south",
            "batch_size": "",
            "message": "Decoy experiment: search ranking v3 rollout to 20% traffic",
        }
    ]

    if scenario == "festival_deadlock":
        # 18:45: enable_dynamic_batching_v2
        audit_records.append({
            "ts": "2026-10-07 18:45:00",
            "kind": "CONFIG_TOGGLE",
            "key": "enable_dynamic_batching_v2",
            "old": "false",
            "new": "true",
            "actor": "ops-automation",
            "scope": "darkstore-blr-south",
            "batch_size": "",
            "message": "Peak surge optimization: enable dynamic multi-order batching v2",
        })

        # 18:48+: Deadlock logs
        deadlock_times = [
            "18:48:12", "18:48:35", "18:48:59", "18:49:15", "18:49:42",
            "18:50:08", "18:51:22", "18:53:40", "18:56:10", "19:02:15",
            "19:15:30", "19:30:12", "20:00:45", "20:30:10", "21:00:00"
        ]
        for dt_str in deadlock_times:
            audit_records.append({
                "ts": f"2026-10-07 {dt_str}",
                "kind": "DB_DEADLOCK",
                "key": "order_alloc_lock",
                "old": "",
                "new": "",
                "actor": "allocator-worker-4",
                "scope": "darkstore-blr-south",
                "batch_size": "5-6",
                "message": "Deadlock detected on resource allocation for batch_size 5-6 items in darkstore-blr-south",
            })

    audit_df = pd.DataFrame(audit_records).sort_values("ts").reset_index(drop=True)
    audit_df.to_csv(out_path / "audit_log.csv", index=False)

    # -------------------------------------------------------------
    # 6. Manifest File
    # -------------------------------------------------------------
    manifest = {
        "scenario": scenario,
        "seed": seed,
        "row_counts": {
            "telemetry": len(telemetry_df),
            "payment_ledger": len(ledger_df),
            "fleet_events": len(fleet_df),
            "support_tickets": len(tickets_df),
            "audit_log": len(audit_df),
        },
        "timeframe": {
            "start": "2026-10-07 18:00:00",
            "end": "2026-10-07 21:30:00",
            "hub": "South Bengaluru",
        }
    }
    with open(out_path / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    return manifest["row_counts"]


def main() -> None:
    """CLI entrypoint for generate_data."""
    parser = argparse.ArgumentParser(description="Generate Clarion synthetic incident data.")
    parser.add_argument(
        "--scenario",
        choices=["festival_deadlock", "gateway_outage"],
        default="festival_deadlock",
        help="Scenario to simulate",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--out", default="data", help="Output directory")
    args = parser.parse_args()

    counts = generate_scenario(args.scenario, args.seed, args.out)
    print(f"Generated {args.scenario} data into '{args.out}': {counts}")


if __name__ == "__main__":
    main()
