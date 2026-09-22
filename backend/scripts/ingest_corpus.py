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


def extract_pages(pdf_path: Path) -> tuple[list[tuple[int, str]], int]:
    """Returns ([(page_number, text)], empty_page_count)."""
    pages, empty = [], 0
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
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
    for pdf in pdfs:
        t0 = time.perf_counter()
        try:
            pages, empty = extract_pages(pdf)
        except Exception as e:
            print(f"  {pdf.name}: UNREADABLE ({type(e).__name__}) — skipped")
            continue
        total_empty += empty
        n_before = len(texts)
        for page_no, page_text in pages:
            for chunk in splitter.split_text(page_text):
                texts.append(chunk)
                # Metadata is what lets a diagnosis cite its source. Without it
                # the demo can only say "the manual says"; with it, it can say
                # which document and which page.
                metadatas.append({"source": pdf.name, "page": page_no})
        print(f"  {pdf.name}: {len(pages)} pages with text, {empty} empty, "
              f"{len(texts) - n_before} chunks ({time.perf_counter() - t0:.1f}s)")

    if not texts:
        print("\nNo text extracted from any PDF. They are almost certainly scans —\n"
              "run scripts/pdf_probe.py, then OCR them with ocrmypdf before retrying.")
        return 1

    print(f"\ntotal: {len(texts)} chunks from {len(pdfs)} PDF(s); {total_empty} pages had no text")
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
