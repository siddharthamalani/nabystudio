#!/usr/bin/env python3
"""Check an art brief BEFORE Codex draws anything (owner rule, 24 Nov 2026).

  python3 engine/lint_brief.py episodes/EpN/art_brief.md

Fails when:
  - a CHARACTER / animation-sheet row asks for furniture or a seat (chair, armchair, sofa, bench, desk, cushion, ...).
    Characters are drawn standing or chest-up, never with furniture; the background provides it.
    (A deliberate exception must say "SEAT-OK: <reason>" in the row.)
  - a talking human is drawn full body while talking (rows saying "mouth open/talk" without "head and shoulders"/"chest-up")
  - a BACKGROUND row for a shot with characters has no empty-space instruction ("clear", "empty", "leave space")
  - any row is missing the no-text rule is not needed per row (AGENTS.md covers it), so it is not checked.
"""
import re, sys

FURNITURE = r"\b(chairs?|armchairs?|sofas?|couch(es)?|benches|bench|stools?|cushions?|pillows?|desks?|tables?|beds?|thrones?|sofa)\b"
NEG = r"\b(no|not|without|never)\b[^.;|]*"


def rows(md):
    for line in md.splitlines():
        if line.startswith("|") and not re.match(r"^\|\s*-", line) and "Save to" not in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3:
                yield cells[0], cells[1], " ".join(cells[2:])


def main(path):
    md = open(path).read(); errors, warns = [], []
    for rid, dest, what in rows(md):
        low = what.lower()
        is_char = any(k in dest for k in ("/characters/", "cast_anim", "/anim/", "_cast/", "/poses/"))
        is_bg = "/backgrounds/" in dest
        if is_char and "seat-ok" not in low:
            positive = re.sub(NEG, " ", low)          # drop "no chair", "without a bench" ...
            hit = re.search(FURNITURE, positive)
            if hit:
                errors.append("%s %s: character drawn with furniture ('%s'). Draw the character without it; the background has the seat." % (rid, dest, hit.group(0)))
            animal = re.search(r"/(cat|mascot|mascot|dog|horse|bird|emu|goose)[^/]*$", dest.strip("`"))
            if not hit and not animal and re.search(r"\b(seated|sitting|sits|sat)\b", positive) and not re.search(r"head and shoulders|head-and-shoulders|chest-up|same as|same image as", low):
                errors.append("%s %s: character is sitting but not chest-up; the artist will invent a chair. Say 'chest-up, no chair' or SEAT-OK." % (rid, dest))
            if re.search(r"mouth (open|mid|half)|talking|explain", low) and not re.search(r"head and shoulders|head-and-shoulders|chest-up|close-up|same image as", low):
                warns.append("%s %s: talking human not specified as head-and-shoulders close-up." % (rid, dest))
        if is_char and "master" not in dest and not re.search(r"assets/references/|_master|same (image )?as|`[^`]+\.png`|\b(f|p|c|m|s)\d+[a-z]?\b framing|of the (f|p|c)\d", low):
            errors.append("%s %s: character row doesn't name its master reference (assets/characters.json). Add 'as <master path>'." % (rid, dest))
        if is_bg and not re.search(r"\b(clear|empty|leave space|left open|plain)\b", low):
            warns.append("%s %s: background has no 'keep this area empty' instruction for the characters." % (rid, dest))
    for e in errors: print("ERROR  ", e)
    for w in warns: print("WARN   ", w)
    print("%d errors, %d warnings" % (len(errors), len(warns)))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main(sys.argv[1])
