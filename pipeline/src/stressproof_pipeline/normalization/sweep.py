"""
Shock sweep utility to identify non-zero bad debt R and establish thresholds.
Matches implementationplan.md §9.8 and C-13.
"""

from stressproof_core.replay import replay


def run_shock_sweep(snapshot: dict) -> dict:
    """
    Evaluates shocks from -1000 to -9000 bps and returns results table.
    """
    results = {}
    for shock_bps in range(-1000, -9500, -500):
        case_file = {
            "scenario": {"asset": "WETH", "shockBps": shock_bps},
            "snapshot": snapshot,
        }
        res = replay(case_file)
        results[shock_bps] = res
    return results


def main():
    print("Running shock sweep...")


if __name__ == "__main__":
    main()
