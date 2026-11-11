"""Command line: python -m resell_advisor <collect|stats|report|demo>"""
import argparse
import sys
from pathlib import Path

from . import db, report, settings, stats, tracker


def main(argv=None):
    ap = argparse.ArgumentParser(prog="resell_advisor")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--db", help="database file (overrides config)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="scan searches and re-check listings (run every 4-6 hours)")
    c.add_argument("--source", choices=["vinted", "olx", "all"], default="all")
    for name, text in (("stats", "print the ranking"), ("report", "write an HTML ranking")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--source", choices=["vinted", "olx", "all"], default="vinted")
        p.add_argument("--by-size", action="store_true")
        p.add_argument("--min-listings", type=int, default=5)
        if name == "report":
            p.add_argument("--out", default="report.html")
    d = sub.add_parser("demo", help="fill a database with simulated data (no network)")
    d.add_argument("--days", type=int, default=45)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # table headers use non-ASCII characters

    cfg = settings.load(args.config)
    path = args.db or ("demo.db" if args.cmd == "demo" else cfg.get("db_path", "resell.db"))
    con = db.connect(path)

    if args.cmd == "collect":
        failed = False
        for source in (db.SOURCES if args.source == "all" else (args.source,)):
            if not tracker.searches_for(cfg, source):
                continue
            result = tracker.run(con, tracker.make_client(cfg, source), cfg, source=source)
            print(source, " ".join(f"{k}={v}" for k, v in result.items()))
            failed = failed or (result["errors"] and not result["seen"])
        return 1 if failed else 0
    if args.cmd == "demo":
        from .demo import simulate
        simulate(con, cfg, days=args.days)
        print(f"Simulated {args.days} days into {path}. Try: "
              f"python -m resell_advisor --db {path} stats")
        return 0

    rows = stats.compute(con, source=args.source, by_size=args.by_size,
                         min_listings=args.min_listings)
    if args.cmd == "stats":
        print(report.summary(con, args.source))
        print(report.text(rows) if rows else "")
    else:
        Path(args.out).write_text(report.html_page(rows, report.summary(con, args.source)),
                                  encoding="utf-8")
        print(f"Wrote {args.out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
