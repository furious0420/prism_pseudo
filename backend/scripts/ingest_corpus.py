"""D3-01 — build the retrieval index from the FAA/EASA manual PDFs.

    python scripts/ingest_corpus.py                 # ingest data/corpus_raw/
    python scripts/ingest_corpus.py --reset         # wipe the index first
    python scripts/ingest_corpus.py --chunk-size 1000 --overlap 150

NOTE ON IMPORTS: the tracker's D3-01 uses import paths that no longer exist.
  langchain.text_splitter           -> ModuleNotFoundError (hard failure)
  langchain_community.vectorstores  -> deprecated, slated for removal
  db.persist()                      -> no-op since Chroma 0.4, deleted here
This file uses the current paths. Do not "fix" it back to the tracker's version.
"""
import argparse
import re
import shutil
import sys
import time
from pathlib import Path

import pdfplumber
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Import the index location rather than redefining it. These two files
# disagreeing is exactly how an index gets written to one path and looked for
# at another.
from models.retrieval import CHROMA_DIR  # noqa: E402

CORPUS_DIR = BACKEND / "data" / "corpus_raw"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Below this many characters a page is effectively blank — usually a scan, a
# cover page or a diagram. Counted and reported so a scanned manual is obvious.
MIN_PAGE_CHARS = 50

# ---------------------------------------------------------------------------
# Corpus cleaning.
#
# pdfplumber extracts everything on the page: running headers, table-of-contents
# lines with dotted leaders, figure captions, bare page numbers. Those chunks
# embed and retrieve just like prose, and score HIGH because they are short and
# topic-dense — a contents line reading "Figure 6-10. Exfoliation Corrosion"
# looks like a perfect match for "exfoliation corrosion treatment" while
# containing no treatment information at all.
#
# Two layers: strip furniture from the page text first, then drop any chunk
# that is still mostly furniture afterwards.
# ---------------------------------------------------------------------------

# The running header, in either order: "9/11/18 AC 43-4B" or "AC 43.13-1B 9/8/98".
# Both appear in the FAA circulars depending on odd/even page.
HEADER_RE = re.compile(
    r"^\s*(?:\d{1,2}/\d{1,2}/\d{2,4}\s+AC\s+[\w.\-]+"
    r"|AC\s+[\w.\-]+\s+\d{1,2}/\d{1,2}/\d{2,4})\s*$", re.M)
# Table-of-contents lines: text, then four or more dots, then a page reference.
TOC_RE = re.compile(r"^.*\.{4,}\s*[\w\-]*\s*$", re.M)
# Bare page numbers: "6-20", "4-4", "Page 17".
PAGENUM_RE = re.compile(r"^\s*(?:Page\s+)?\d+[-–]?\d*\s*$", re.M)
# A caption occupying its own line.
CAPTION_RE = re.compile(r"^\s*(?:Figure|Table|FIGURE|TABLE)\s+[\d.\-]+\.?.*$", re.M)
# A STANDALONE caption line, short enough that it cannot also be carrying prose.
# Without the length guard, a line where extraction merged a caption into the
# following sentence would lose the sentence too.
CAPTION_LINE_RE = re.compile(
    r"^[ \t]*(?:Figure|Table|FIGURE|TABLE)\s+[\d.\-]+\.?[^\n]{0,110}$", re.M)

MIN_WORDS = 25          # real prose in an 800-char chunk runs well over this
MIN_ALPHA_RATIO = 0.65  # letters and spaces as a share of the chunk
MAX_CAPTION_SHARE = 0.5 # over half the chunk being captions = furniture


def extract_page_text(page) -> str:
    """Extract a page, reading COLUMNS DOWN rather than lines ACROSS.

    FAA circulars are two-column. pdfplumber's default extract_text() walks the
    page line by line across its full width, so it glues the left column's line
    to the right column's line and produces text like:

        "Corrosion removal begins with cleaning the Stress corrosion cracking
         affected area to remove all grease and soil. results from sustained..."

    Every sentence is broken by an unrelated fragment. Embeddings of that are
    close to meaningless, which is why retrieved passages read as nonsense and
    the model sometimes declined rather than answer from them.

    We find the gutter — the vertical band crossed by the fewest words — and
    extract each side separately.
    """
    words = page.extract_words()
    if not words:
        return ""

    # Only look for a gutter in the middle 40% of the page.
    lo, hi = page.width * 0.3, page.width * 0.7
    best_x, best_cross = None, len(words)
    for frac in range(30, 71, 2):
        x = page.width * frac / 100
        crossing = sum(1 for w in words if w["x0"] < x < w["x1"])
        if crossing < best_cross:
            best_x, best_cross = x, crossing

    left = [w for w in words if w["x1"] <= best_x]
    right = [w for w in words if w["x0"] >= best_x]

    # Two columns only if almost nothing crosses the gutter AND both sides
    # carry real content. A single-column page fails the second test.
    two_column = (
        best_x is not None
        and best_cross <= max(2, 0.02 * len(words))
        and min(len(left), len(right)) >= 0.2 * len(words)
    )
    if not two_column:
        return page.extract_text() or ""

    l = page.crop((0, 0, best_x, page.height)).extract_text() or ""
    r = page.crop((best_x, 0, page.width, page.height)).extract_text() or ""
    return (l.strip() + "\n" + r.strip()).strip()


def clean_page(text: str) -> str:
    """Strip running headers, contents lines and bare page numbers."""
    text = HEADER_RE.sub("", text)
    text = TOC_RE.sub("", text)
    text = CAPTION_LINE_RE.sub("", text)
    text = PAGENUM_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def is_low_information(chunk: str) -> bool:
    """True when a chunk is document furniture rather than content."""
    stripped = chunk.strip()
    if not stripped:
        return True

    words = [w for w in re.findall(r"[A-Za-z]{3,}", stripped)]
    if len(words) < MIN_WORDS:
        return True

    alpha = sum(c.isalpha() or c.isspace() for c in stripped)
    if alpha / len(stripped) < MIN_ALPHA_RATIO:
        return True

    caption_chars = sum(len(m.group(0)) for m in CAPTION_RE.finditer(stripped))
    if caption_chars / len(stripped) > MAX_CAPTION_SHARE:
        return True

    return False


def extract_pages(pdf_path: Path) -> tuple[list[tuple[int, str]], int]:
    """Returns ([(page_number, text)], empty_page_count)."""
    pages, empty = [], 0
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = clean_page(extract_page_text(page).strip())
            if len(text) < MIN_PAGE_CHARS:
                empty += 1
                continue
            pages.append((i, text))
    return pages, empty


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete the existing index first")
    ap.add_argument("--chunk-size", type=int, default=800)
    ap.add_argument("--overlap", type=int, default=100)
    ap.add_argument("--corpus", type=Path, default=CORPUS_DIR)
    args = ap.parse_args()

    pdfs = sorted(args.corpus.rglob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {args.corpus}")
        print("Download the FAA manuals into that folder first (see Day 3 notes).")
        return 1

    if args.reset and CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
        print(f"wiped {CHROMA_DIR}")

    print(f"corpus : {args.corpus}\nchunk  : {args.chunk_size} chars, {args.overlap} overlap\n")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=args.chunk_size,
        chunk_overlap=args.overlap,
        # Prefer real paragraph/sentence boundaries so chunks stay readable —
        # a chunk cut mid-sentence retrieves badly and reads worse in a demo.
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    texts, metadatas = [], []
    total_empty = 0
    total_dropped = 0
    for pdf in pdfs:
        t0 = time.perf_counter()
        try:
            pages, empty = extract_pages(pdf)
        except Exception as e:
            print(f"  {pdf.name}: UNREADABLE ({type(e).__name__}) — skipped")
            continue
        total_empty += empty
        n_before = len(texts)
        dropped = 0
        for page_no, page_text in pages:
            for chunk in splitter.split_text(page_text):
                if is_low_information(chunk):
                    dropped += 1
                    continue
                texts.append(chunk)
                # Metadata is what lets a diagnosis cite its source. Without it
                # the demo can only say "the manual says"; with it, it can say
                # which document and which page.
                metadatas.append({"source": pdf.name, "page": page_no})
        total_dropped += dropped
        print(f"  {pdf.name}: {len(pages)} pages with text, {empty} empty, "
              f"{len(texts) - n_before} chunks kept, {dropped} furniture dropped "
              f"({time.perf_counter() - t0:.1f}s)")

    if not texts:
        print("\nNo text extracted from any PDF. They are almost certainly scans —\n"
              "run scripts/pdf_probe.py, then OCR them with ocrmypdf before retrying.")
        return 1

    kept_pct = 100 * len(texts) / max(1, len(texts) + total_dropped)
    print(f"\ntotal: {len(texts)} chunks from {len(pdfs)} PDF(s); "
          f"{total_empty} pages had no text")
    print(f"       {total_dropped} chunks dropped as document furniture "
          f"(contents lines, captions, page headers) — {kept_pct:.0f}% kept")
    if kept_pct < 60:
        print("       WARNING: over 40% dropped. That is more than expected — check a\n"
              "       few dropped chunks before trusting this index.")
    if total_empty > len(texts) * 0.5:
        print("WARNING: a lot of pages yielded no text. Check pdf_probe.py — some of\n"
              "         these PDFs may be scanned and silently contributing nothing.")

    print(f"\nloading embedding model ({EMBED_MODEL}) ...")
    t0 = time.perf_counter()
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    print(f"  loaded in {time.perf_counter() - t0:.1f}s")

    print("embedding and indexing (first run downloads the model, ~90 MB) ...")
    t0 = time.perf_counter()
    Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        persist_directory=str(CHROMA_DIR),
        # Chroma defaults to L2 (Euclidean). MiniLM is trained for COSINE
        # similarity, and L2 both ranks worse and produces scores outside the
        # 0-1 range that LangChain's relevance helper expects. Set it here, at
        # creation — an existing collection keeps whatever metric it was built
        # with, so changing this later needs --reset.
        collection_metadata={"hnsw:space": "cosine"},
    )
    # No db.persist() — Chroma writes as it goes since 0.4.x.
    print(f"  indexed {len(texts)} chunks in {time.perf_counter() - t0:.1f}s")
    print(f"\nindex written to {CHROMA_DIR}")
    print("next: python scripts/verify_retrieval.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
