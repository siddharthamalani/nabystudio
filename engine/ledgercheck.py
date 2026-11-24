#!/usr/bin/env python3
"""Claim-ledger check: receipts must come from real sources, not from an encyclopedia summary.
research.md ledger rows look like `| C1 | claim | exact wording | source | hedge |`. Source codes (W1, P1…) are defined in lines
like `- W1 = Wikipedia, "…"`.
Fails when:
  - more than 25% of claims rest ONLY on Wikipedia (use Wikipedia as a map to the sources, then quote the source itself:
    diaries on archive.org, Hansard, newspapers, museum/collection pages, books);
  - a claim has no exact wording (empty or "not found" in the wording column);
  - the script's "The Receipts" section credits Wikipedia.
  python3 engine/ledgercheck.py episodes/EpN"""
import os, re, sys


def check(ep):
    md = open(os.path.join(ep, "research.md"), encoding="utf-8").read()
    wiki = {m.group(1) for m in re.finditer(r"^\s*-\s*([A-Z]\d+)\s*=\s*.*wikipedia", md, re.M | re.I)}
    rows = [l for l in md.splitlines() if re.match(r"^\|\s*C\d+\s*\|", l)]
    errs, wiki_only = [], []
    for r in rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        cid, words, src = cells[0], (cells[2] if len(cells) > 2 else ""), (cells[3] if len(cells) > 3 else "")
        refs = set(re.findall(r"\b([A-Z]\d+)\b", src + " " + words)) - {cid}
        others = [x for x in refs if x not in wiki]
        named = re.search(r"diary|journal|hansard|archive\.org|museum|collection|times|register|letter|\bbook\b|press|gazette|\.gov|\.ac\.|parliament", src + " " + words, re.I)
        if (refs & wiki or "wikipedia" in (src + words).lower()) and not others and not named:
            wiki_only.append(cid)
        if not words or words.lower().startswith("not found") or words == "—":
            errs.append("%s has no exact source wording" % cid)
    if rows and len(wiki_only) / len(rows) > 0.25:
        errs.append("%d of %d claims rest only on Wikipedia (max 25%%): %s. Quote the underlying source instead."
                    % (len(wiki_only), len(rows), ", ".join(wiki_only)))
    sp = os.path.join(ep, "script.md")
    if os.path.exists(sp):
        s = open(sp, encoding="utf-8").read()
        m = re.search(r"^##\s*The Receipts.*?$(.*?)(?=^##\s|\Z)", s, re.M | re.S | re.I)
        if m and "wikipedia" in m.group(1).lower(): errs.append("script 'The Receipts' credits Wikipedia; credit the underlying sources")
    if not rows: errs.append("no claim rows (| C1 | …) found in research.md")
    for e in errs: print("✗", e)
    print("ledgercheck %s: %s" % (ep, "OK" if not errs else "%d problems" % len(errs)))
    return len(errs)


if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(0)
    sys.exit(1 if check(sys.argv[1]) else 0)
