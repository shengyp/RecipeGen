import re
import difflib
import xml.etree.ElementTree as ET

INFILE = "recipe_2020_2026.xml"
OUTFILE = "bibliography_2020_2026.md"
YEAR_MIN = 2020

tree = ET.parse(INFILE)
root = tree.getroot()

records = []
for hit in root.findall(".//hits/hit"):
    info = hit.find("info")
    authors = [a.text.strip() for a in info.findall("./authors/author") if a.text]
    title = (info.findtext("title") or "").strip()
    venue = (info.findtext("venue") or "").strip()
    pages = (info.findtext("pages") or "").strip()
    volume = (info.findtext("volume") or "").strip()
    year = (info.findtext("year") or "").strip()
    access_el = info.find("access")
    access = access_el.text.strip() if access_el is not None and access_el.text else ""
    ee = (info.findtext("ee") or "").strip()
    records.append({
        "authors": authors, "title": title, "venue": venue,
        "pages": pages, "volume": volume, "year": year,
        "access": access, "ee": ee,
        "title_norm": re.sub(r"[^a-z0-9]+", "", title.lower()),
    })

def clean_authors(names):
    return [re.sub(r"\s+\d{4}$", "", n) for n in names]

def arxiv_pdf(ee):
    m = re.search(r"10\.48550/arXiv\.(.+)$", ee)
    if m:
        return "https://arxiv.org/pdf/" + m.group(1).strip(".")
    m = re.search(r"arxiv\.org/abs/([^/?#]+)", ee)
    if m:
        return "https://arxiv.org/pdf/" + m.group(1).strip(".")
    return None

def pdf_url(rec, by_title):
    ee = rec["ee"]
    p = arxiv_pdf(ee) if ee else None
    if p:
        return p
    if ee.lower().endswith(".pdf"):
        return ee
    m = re.match(r"(https?://aclanthology\.org/[^/]+)/?$", ee)
    if m:
        return m.group(1) + ".pdf"
    if rec["access"] == "open" and ee:
        for r in by_title.get(rec["title_norm"], []):
            if r is rec:
                continue
            q = arxiv_pdf(r["ee"]) or (r["ee"] if r["ee"].lower().endswith(".pdf") else None)
            if q:
                return q
        return ee
    for r in by_title.get(rec["title_norm"], []):
        if r is rec:
            continue
        q = arxiv_pdf(r["ee"]) or (r["ee"] if r["ee"].lower().endswith(".pdf") else None)
        if q:
            return q
    return None

by_title = {}
for r in records:
    by_title.setdefault(r["title_norm"], []).append(r)

def show_venue(r):
    return r["venue"]

def formal_score(r):
    v = r["venue"]
    return (0 if v.startswith("CoRR") else 2,
            0 if ("@" in v or "Workshop" in v) else 1)

def pick_formal(group):
    return max(group, key=formal_score)

records = [r for r in records if int(r["year"]) >= YEAR_MIN]

pool = {}
for r in records:
    pool.setdefault(r["title_norm"], []).append(r)

dropped = 0
kept = []
for group in pool.values():
    if len(group) > 1:
        dropped += len(group) - 1
    kept.append(pick_formal(group))

def first_family(name):
    name = re.sub(r"\s+\d{4}$", "", name)
    toks = name.split()
    return toks[-1].lower() if toks else ""

# fuzzy pass: drop CoRR preprints whose published version got renamed
fuzzy_dropped = 0
final = []
for r in kept:
    match = None
    if r["venue"].startswith("CoRR"):
        for f in kept:
            if f is r or f["venue"].startswith("CoRR"):
                continue
            if abs(int(r["year"]) - int(f["year"])) > 2:
                continue
            if not r["authors"] or not f["authors"]:
                continue
            if first_family(r["authors"][0]) != first_family(f["authors"][0]):
                continue
            ratio = difflib.SequenceMatcher(None, r["title_norm"], f["title_norm"]).ratio()
            same_authors = tuple(sorted(clean_authors(r["authors"]))) == tuple(sorted(clean_authors(f["authors"])))
            if ratio >= 0.85 or (same_authors and ratio >= 0.75):
                match = f
                break
    if match is not None:
        by_title.setdefault(match["title_norm"], []).append(r)
        fuzzy_dropped += 1
    else:
        final.append(r)
records = final
records.sort(key=lambda r: (-int(r["year"]), r["title_norm"]))

def fmt_author_list(names):
    return ", ".join(clean_authors(names))

def fmt(r, i):
    title = r["title"]
    if not title.endswith("."):
        title += "."
    authors = fmt_author_list(r["authors"])
    pdf = pdf_url(r, by_title)
    tail = []
    if r["volume"]:
        tail.append(r["volume"])
    if r["pages"]:
        tail.append(r["pages"])
    tail.append(r["year"])
    venue = show_venue(r)
    first = f"**{title}**" + (f" `{venue}`" if venue else "")
    if pdf:
        second = f"*{authors}* [[PDF]({pdf})], " + ", ".join(tail) + "."
    else:
        second = f"*{authors}*, " + ", ".join(tail) + "."
    # Continuation must be indented to the list marker's content column:
    # "1. " -> 3, "10. " -> 4, "100. " -> 5 spaces. A fixed 4 spaces breaks
    # entries numbered 100+ (the author line falls out of the list item).
    indent = " " * max(4, len(str(i)) + 2)
    return f"{i}. {first}\n\n{indent}{second}"

groups = {}
for r in records:
    groups.setdefault(r["year"], []).append(r)

blocks = []
for year in sorted(groups, key=int, reverse=True):
    lines = [f"## {year}", ""]
    for i, r in enumerate(groups[year], 1):
        entry = fmt(r, i)
        lines.append(entry)
        lines.append("")
    blocks.append("\n".join(lines).rstrip())

out = "\n\n".join(blocks) + "\n"
with open(OUTFILE, "w", encoding="utf-8", newline="\n") as f:
    f.write(out)

counts = {y: len(rs) for y, rs in groups.items()}
print("entries:", len(records), "dropped duplicates:", dropped + fuzzy_dropped, "(exact:", dropped, ", fuzzy:", fuzzy_dropped, ")")
print("by year:", dict(sorted(counts.items(), key=lambda kv: -int(kv[0]))))
