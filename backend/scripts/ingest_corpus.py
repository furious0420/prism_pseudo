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


# A gutter is looked for only in the middle of the page — a margin is not a
# gutter. At most this many words may cross it: a full-width heading or table
# row spanning the columns must not veto an otherwise obvious column break.
MAX_GUTTER_CROSSINGS = 2
# And the columns either side must be substantially denser than the gutter,
# so a sparse page (a figure, a title) is not mistaken for two columns.
MIN_SIDE_DENSITY = 6
GUTTER_ZONE = (0.35, 0.65)


def find_gutter(page) -> float | None:
    """The x of the column separator, or None if the page is single-column.

    THE BUG THIS FIXES: these FAA circulars are two-column, and pdfplumber's
    default extract_text() reads straight across the full page width, so it
    interleaves the columns line by line:

        "(d) Check ribs on either side of strut  physical damage or decay."
          ^ left column                           ^ right column, glued on

    Every chunk indexed that way is semantically shredded, which is what made
    the model look stupid — it was reasoning over half-sentences.

    The gutter is DETECTED, not assumed. A fixed width/2 split is wrong: real
    gutters here sit anywhere from x=299 to x=313, and splitting at the wrong
    x cuts words in half ("t physical damage").
    """
    words = page.extract_words()
    if not words:
        return None

    # How many words cross each x-position, at 1pt resolution. Counting
    # crossings rather than demanding a fully empty band matters twice over:
    # real gutters here can be as narrow as 1-2pt, and a single full-width
    # heading would otherwise veto the whole page.
    n = int(page.width) + 2
    crossings = [0] * n
    for w in words:
        for x in range(int(w["x0"]), min(int(w["x1"]) + 1, n)):
            crossings[x] += 1

    lo, hi = int(page.width * GUTTER_ZONE[0]), int(page.width * GUTTER_ZONE[1])
    if hi <= lo:
        return None
    gutter = min(range(lo, hi), key=lambda x: crossings[x])
    if crossings[gutter] > MAX_GUTTER_CROSSINGS:
        return None

    # Require real text on BOTH sides, else a sparse figure page with an
    # incidental gap would be split into two half-empty "columns".
    left_density = max(crossings[lo:gutter] or [0])
    right_density = max(crossings[gutter:hi] or [0])
    if min(left_density, right_density) < MIN_SIDE_DENSITY:
        return None
    return gutter


# Table-of-contents lines are mostly dot leaders — "6-29. General ......... 6-5".
# They carry almost no information but embed near any query mentioning their
# heading words, so they win retrieval slots that should hold actual guidance.
# Measured on this corpus: ToC chunks run 0.20-0.39 alphanumeric, real prose
# 0.81-0.82. Nothing falls between, so this threshold is not a close call.
MIN_ALNUM_RATIO = 0.55


def is_low_information(text: str) -> bool:
    """True for contents/index filler that should never reach the model."""
    if not text:
        return True
    alnum = sum(c.isalnum() for c in text)
    return (alnum / len(text)) < MIN_ALNUM_RATIO


def clean_text(text: str) -> str:
    """Repair artefacts of PDF text extraction.

    These circulars are typeset with hyphenation, so extracted text is full of
    words split across lines — "pro­\ntected", "ap­\nplying". The U+00AD is a
    SOFT HYPHEN, invisible but present, and it fragments the word for both the
    embedding model and the LLM: "protected" and "pro" + "tected" are not the
    same token sequence, so retrieval quietly loses recall on any hyphenated
    term.
    """
    # Soft hyphen immediately before a line break: the word continues.
    text = re.sub(r"­\s*\n\s*", "", text)
    # Any remaining soft hyphens are invisible noise.
    text = text.replace("­", "")
    # Ordinary hyphen at end of line joining a word.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return text


def extract_pages(pdf_path: Path, single_column: bool = False
                  ) -> tuple[list[tuple[int, str]], int, int]:
    """Returns ([(page_number, text)], empty_page_count, two_column_page_count)."""
    pages, empty, two_col = [], 0, 0
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            gutter = None if single_column else find_gutter(page)
            if gutter:
                # Read the left column fully, then the right — the order a
                # human reads it in, and the order the sentences make sense in.
                left = page.crop((0, 0, gutter, page.height)).extract_text() or ""
                right = page.crop((gutter, 0, page.width, page.height)).extract_text() or ""
                text = clean_text("\n".join([left.strip(), right.strip()])).strip()
                two_col += 1
            else:
                # Single-column, or a table/figure/contents page where no
                # gutter exists. Falling back is correct, not a failure.
                text = clean_text(page.extract_text() or "").strip()
            if len(text) < MIN_PAGE_CHARS:
                empty += 1
                continue
            pages.append((i, text))
    return pages, empty, two_col


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete the existing index first")
    ap.add_argument("--chunk-size", type=int, default=800)
    ap.add_argument("--overlap", type=int, default=100)
    ap.add_argument("--corpus", type=Path, default=CORPUS_DIR)
    ap.add_argument("--single-column", action="store_true",
                    help="force whole-page extraction (the pre-fix behaviour)")
    args = ap.parse_args()

    pdfs = sorted(args.corpus.rglob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {args.corpus}")
        print("Download the FAA manuals into that folder first (see Day 3 notes).")
        return 1

    if args.reset and CHROMA_DIR.exists():
        try:
            shutil.rmtree(CHROMA_DIR)
        except PermissionError as e:
            # Windows will not delete a file another process has open, and the
            # Flask backend holds the Chroma connection for the life of the
            # process. The raw traceback points at data_level0.bin, which says
            # nothing about the actual cause.
            print(f"\nCannot wipe {CHROMA_DIR} — a process is still using it.")
            print(f"  ({e.__class__.__name__}: {e.filename})")
            print("  fix -> stop the backend (python app.py) and any open Python"
                  " shell that imported models.retrieval, then re-run.")
            return 1
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
    dropped = 0
    for pdf in pdfs:
        t0 = time.perf_counter()
        try:
            pages, empty, two_col = extract_pages(pdf, args.single_column)
        except Exception as e:
            print(f"  {pdf.name}: UNREADABLE ({type(e).__name__}) — skipped")
            continue
        total_empty += empty
        n_before = len(texts)
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
        print(f"  {pdf.name}: {len(pages)} pages with text, {empty} empty, "
              f"{two_col} two-column, {len(texts) - n_before} chunks "
              f"({time.perf_counter() - t0:.1f}s)")

    if not texts:
        print("\nNo text extracted from any PDF. They are almost certainly scans —\n"
              "run scripts/pdf_probe.py, then OCR them with ocrmypdf before retrying.")
        return 1

    print(f"\ntotal: {len(texts)} chunks from {len(pdfs)} PDF(s); "
          f"{total_empty} pages had no text; "
          f"{dropped} low-information chunks dropped")
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
