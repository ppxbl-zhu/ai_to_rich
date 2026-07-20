from pathlib import Path
import argparse

from .engine import make_demo, run_paper


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["demo", "run"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    data = root / "data" / ("demo_market.csv" if args.command == "demo" else "market.csv")
    if args.command == "demo":
        make_demo(data)
        print(f"演示数据已生成：{data}")
    else:
        print(run_paper(root / "config.json", data, root / "state", root / "reports"))


if __name__ == "__main__":
    main()
