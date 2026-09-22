"""Pre-Day-3 check — are the FAA/EASA manuals real text, or scanned images?

    python scripts/pdf_probe.py backend/data/corpus_raw

D3-01 assumes pdfplumber's extract_text() returns text. On a scanned manual it
returns empty strings and the whole retrieval track stalls on Day 3. Five
minutes today saves that. If pages come back EMPTY you need an OCR pass first
(ocrmypdf locally, or Amazon Textract) before ingesting.
"""
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber not installed.  pip install pdfplumber")

# Below this many chars on a page, it is almost certainly a scan, not text.
TEXT_THRESHOLD = 100
SAMPLE_PAGES = 5


def probe(pdf_path: Path) -> str:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            n = len(pdf.pages)
            counts = []
            for page in pdf.pages[:SAMPLE_PAGES]:
                counts.append(len((page.extract_text() or "").strip()))
    except Exception as e:
        print(f"  {pdf_path.name}: UNREADABLE ({e})")
        return "ERROR"

    avg = sum(counts) / len(counts) if counts else 0
    verdict = "TEXT" if avg >= TEXT_THRESHOLD else "SCANNED"
    flag = "     " if verdict == "TEXT" else "  <-- "
    print(f"  {pdf_path.name}: {verdict}{flag}{n} pages, "
          f"avg {avg:.0f} chars/page over first {len(counts)}")
    return verdict


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "backend/data/corpus_raw")
    pdfs = sorted(root.rglob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {root.resolve()}")
        print("Put the FAA/EASA manuals there before Day 3 (D3-01 step 2).")
        return

    print(f"Probing {len(pdfs)} PDF(s) in {root.resolve()}\n")
    results = [probe(p) for p in pdfs]

    scanned = results.count("SCANNED")
    print("\n=== VERDICT ===")
    if scanned == 0:
        print("All PDFs are digital text. D3-01 works as written with pdfplumber.")
    else:
        print(f"{scanned}/{len(results)} PDF(s) are SCANNED IMAGES — extract_text() will")
        print("return empty strings and Day 3 retrieval will have nothing to index.")
        print("\nFix BEFORE Day 3, pick one:")
        print("  A) local OCR  : pip install ocrmypdf  (needs tesseract on PATH)")
        print("                  ocrmypdf in.pdf out.pdf   -> keeps the PoC fully offline")
        print("  B) AWS Textract: better on multi-column/table layouts, adds a 5th service")
        print("  Recommend A — corpus ingestion is a one-time dev step, so local OCR")
        print("  costs nothing and does not weaken the offline story.")


if __name__ == "__main__":
    main()
