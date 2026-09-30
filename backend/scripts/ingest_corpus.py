"""D3-01 — build the retrieval index from the FAA/EASA manual PDFs.

    python scripts/ingest_corpus.py                 # ingest data/corpus_raw/
    python scripts/ingest_corpus.py --reset         # wipe the index first
    python scripts/ingest_corpus.py --chunk-size 1000 --overlap 150

NOTE ON IMPORTS: the tracker's D3-01 uses import paths that no longer exist.
  langchain.text_splitter           -> ModuleNotFoundError (hard failure)
  langchain_community.vectorstores  -> deprecated, slated for removal
  db.persist()                      -> no-op since Chroma 0.4, deleted here
This file uses the current paths. Do not "fix" it back to the tracker's version.

PROVENANCE: this file merges two independent fixes to the same underlying
problem — the indexed chunks were not readable English, which is why the model
looked stupid no matter how the prompt was tuned.

  * Column-aware extraction (find_gutter) was written on this branch and kept,
    on measurement rather than preference. Run head to head over all 1,350
    pages, his variant fires on MORE pages (537 vs 434 on AC_43.13-1B, 532 vs
    496 on AC_65-15A), and where both fire they agree almost perfectly
    (431/434). The extra pages are not a gain: sampled and inspected, they are
    sparse FIGURE pages — a caption and a page number, no prose — which our
    MIN_SIDE_DENSITY guard rejects on purpose. His acceptance test also allows
    0.02*len(words) to straddle the split rather than an absolute 2, so on 7%
    of the pages he accepts the split cuts 3-7 words in half. Ours is the more
    conservative detector and that is the right trade here.
  * The furniture stripping (clean_page and its regexes) and the much stronger
    is_low_information are Anish's, adopted wholesale. Ours only dropped
    dot-leader contents lines; his also removes running headers, bare page
    numbers and standalone figure/table captions, which were still riding
    along inside otherwise-good chunks.
  * clean_text (hyphenation repair) is ours, and has no counterpart in his.

Both halves are needed. Neither alone produced clean chunks.
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
# Layer 1 — column-aware extraction.
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Layer 2 — corpus cleaning.
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
# The trailing (?:\s+CHG\s+\d+)? matters: AC 43.13-1B's revised pages carry
# "9/27/01 AC 43.13-1B CHG 1", and without it the $ anchor failed and the whole
# header rode into the chunk. That alone accounted for most of a measured 8.5%
# of chunks still opening with a date.
HEADER_RE = re.compile(
    r"^\s*(?:\d{1,2}/\d{1,2}/\d{2,4}\s+AC\s+[\w.\-]+(?:\s+CHG\s+\d+)?"
    r"|AC\s+[\w.\-]+(?:\s+CHG\s+\d+)?\s+\d{1,2}/\d{1,2}/\d{2,4})\s*$", re.M)
# A date alone on its line — the other half of a running header, left behind
# when column cropping separated it from the AC number. A line that is nothing
# but a date is never content.
DATE_LINE_RE = re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{2,4}\s*$", re.M)
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
MAX_CAPTION_SHARE = 0.5  # over half the chunk being captions = furniture


# A contents page announces itself. These pages survived every other filter
# because their section titles are real words in quantity, so they passed the
# MIN_WORDS test while containing no guidance at all — exactly the chunks that
# win a retrieval slot and then tell the model nothing.
CONTENTS_PAGE_RE = re.compile(
    r"CONTENTS\s*\(CONTINUED\)|^\s*(?:TABLE OF )?CONTENTS\s*$|^\s*Paragraph\s+Page\s*$",
    re.M)


def is_contents_page(text: str) -> bool:
    """True for a table-of-contents page, which should not be indexed at all."""
    return CONTENTS_PAGE_RE.search(text) is not None


def clean_page(text: str) -> str:
    """Strip running headers, contents lines and bare page numbers."""
    text = HEADER_RE.sub("", text)
    text = DATE_LINE_RE.sub("", text)
    text = TOC_RE.sub("", text)
    text = CAPTION_LINE_RE.sub("", text)
    text = PAGENUM_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def is_low_information(chunk: str) -> bool:
    """True when a chunk is document furniture rather than content."""
    stripped = chunk.strip()
    if not stripped:
        return True

    words = re.findall(r"[A-Za-z]{3,}", stripped)
    if len(words) < MIN_WORDS:
        return True

    alpha = sum(c.isalpha() or c.isspace() for c in stripped)
    if alpha / len(stripped) < MIN_ALPHA_RATIO:
        return True

    caption_chars = sum(len(m.group(0)) for m in CAPTION_RE.finditer(stripped))
    if caption_chars / len(stripped) > MAX_CAPTION_SHARE:
        return True

    return False


def extract_pages(pdf_path: Path, single_column: bool = False
                  ) -> tuple[list[tuple[int, str]], int, int, int]:
    """Returns ([(page_no, text)], empty_pages, two_column_pages, contents_pages)."""
    pages, empty, two_col, contents = [], 0, 0, 0
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            gutter = None if single_column else find_gutter(page)
            if gutter:
                # Read the left column fully, then the right — the order a
                # human reads it in, and the order the sentences make sense in.
                left = page.crop((0, 0, gutter, page.height)).extract_text() or ""
                right = page.crop((gutter, 0, page.width, page.height)).extract_text() or ""
                raw = "\n".join([left.strip(), right.strip()])
                two_col += 1
            else:
                # Single-column, or a table/figure/contents page where no
                # gutter exists. Falling back is correct, not a failure.
                raw = page.extract_text() or ""
            # Repair hyphenation BEFORE stripping furniture: the furniture
            # patterns are line-anchored, and rejoining split words first means
            # they match against whole lines rather than fragments.
            text = clean_text(raw).strip()
            # Checked BEFORE cleaning strips the very markers that identify it.
            if is_contents_page(text):
                contents += 1
                continue
            text = clean_page(text)
            if len(text) < MIN_PAGE_CHARS:
                empty += 1
                continue
            pages.append((i, text))
    return pages, empty, two_col, contents


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
    total_dropped = 0
    for pdf in pdfs:
        t0 = time.perf_counter()
        try:
            pages, empty, two_col, contents = extract_pages(pdf, args.single_column)
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
              f"{contents} contents, {two_col} two-column, "
              f"{len(texts) - n_before} chunks kept, "
              f"{dropped} furniture dropped ({time.perf_counter() - t0:.1f}s)")

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
