"""
McMaster-Carr Sourcing Copilot — one-shot part finder.

Usage:
    python main.py "socket head cap screw"
"""

import csv
import sys
import time

import config  # noqa: F401 — loads .env + logging
from mcmaster_scraper import search_mcmaster, McmasterPartQuote


def print_table(quotes: list[McmasterPartQuote]) -> None:
    print(f"\n  {'#':<4} {'Price':<12} {'Avail':<16} {'Name':<44} {'Part Number'}")
    print(f"  {'-'*4} {'-'*12} {'-'*16} {'-'*44} {'-'*16}")
    for i, q in enumerate(quotes, 1):
        avail = q.availability[:14] + ".." if len(q.availability) > 16 else q.availability
        name = q.name[:42] + ".." if len(q.name) > 44 else q.name
        print(f"  {i:<4} ${q.price_usd:<11.2f} {avail:<16} {name:<44} {q.part_number}")


def save_csv(quotes: list[McmasterPartQuote], path: str = "mcmaster_results.csv") -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "price_usd", "part_number", "availability", "url"])
        for q in quotes:
            w.writerow([q.name, q.price_usd, q.part_number, q.availability, q.url])
    print(f"\n  Saved to {path}")


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python main.py "your search query"')
        print('Example: python main.py "socket head cap screw"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    t0 = time.perf_counter()

    print(f'\n  Searching McMaster-Carr for "{query}" ...\n')

    quotes = search_mcmaster(query)

    if not quotes:
        print("\n  No results found. Check the logs above for errors.")
        sys.exit(1)

    # Sort by price
    quotes.sort(key=lambda q: q.price_usd)

    print_table(quotes)

    best = quotes[0]
    print(f"""
  ============================================================
  BEST DEAL
  ============================================================
  Product:      {best.name}
  Price:        ${best.price_usd:.2f}
  Availability: {best.availability}
  Part #:       {best.part_number}
  URL:          {best.url}
  ============================================================
""")

    save_csv(quotes)

    elapsed = time.perf_counter() - t0
    print(f"  Done in {elapsed:.1f}s\n")


if __name__ == "__main__":
    main()
