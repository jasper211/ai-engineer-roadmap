Extraction reliability release: six fixes for silent content loss or silent wrong answers, plus the first changelog generated from commit messages.

**Highlights**

- **Scanned PDFs fail fast.** An image-only PDF used to run the whole extraction chain — Docling across every page in technical mode — before failing with a message about Unicode sanitization. It now stops on the first pages in ~0.01s and tells you to run `ocrmypdf` (#130), and the docs finally state the limit (#132).
- **Real words stopped being deleted.** Page-edge cleanup treated any short word built from `ivxlcdm` as a page number, so "MIX", "CIVIL" and "VIVID" vanished when they were alone on a page's first or last line (#119).
- **Table-of-contents detection no longer depends on input order.** With multiple sources, `has_toc` was re-derived over the joined corpus and its 30k-char window only ever covered the first book — the same two books in the opposite order gave opposite answers (#114).
- **A single unreadable file no longer aborts the batch** (#120), and `~` in a quoted glob is expanded, so the README's own example works (#118).
- **CJK tables of contents with inserted whitespace** (`目 录`, including the ideographic space) are detected (#112).
- **The generated-skill scanner reads nested chapters** and reports Markdown it left out of scope instead of printing an unqualified pass (#115).

Thanks to @Zhengzhongjie, @Hotragn, @aryansk and @dex0shubham for these fixes.

---

### Added
- Warn on unknown CLI flags instead of silently ignoring (#89)
- Make the site indexable and shareable
- Add Booklin banner and hand-made share card
- Apply pdftotext cleanup to pypdf and pdfminer paths too (#101)

### Documentation
- Sync architecture, skill spec, and README with v1.3.0
- Reserve README project listings for sponsors
- Add Booklin mascot to the README (#106)
- Split README into pages and add Booklin mascot set (#110)
- State that scanned PDFs need OCR first (#132)

### Fixed
- Gate lowercase Roman behind heading context, add FP coverage (#88)
- CJK-aware token estimate (rescued from #70) (#103)
- Support documented help flags (#97)
- Emit block boundaries at end tags in the stdlib parser (#107)
- Skip control destination groups in the dependency-free fallback (#109)
- Scrub bidirectional controls and remaining invisible code points (#108)
- Write metadata.json as UTF-8 (#105)
- Detect Markdown-prefixed chapter headings (#91) (#92)
- Reserve the banner's space on the site build
- Abort early on scanned PDFs with an OCR hint (#130)
- Stop edge-of-page cleanup deleting real one-word lines (#119)
- Expand `~` in input paths (#118)
- Skip an unreadable source instead of aborting the batch (#120)
- Detect a table of contents in any source, not just the first (#114)
- Scan nested chapters and report markdown left out of scope (#115)
- Detect whitespace-separated CJK ToC headers (#112)
- Stop duplicating the PR number in generated entries (#131)

### Miscellaneous
- Untrack stale compiled bytecode (#94)
- Generate CHANGELOG from commits with git-cliff (#104)

### Notes on selected changes

*Written by hand before this file became generated; kept for the detail the
one-line entries above do not carry.*

**CJK-aware token estimate** — `estimate_tokens` now counts CJK codepoints
directly (against `CJK_CHARS_PER_TOKEN`) instead of whitespace-delimited words,
fixing a ~1000× undercount for space-less Chinese/Japanese books in the cost
pre-flight. Latin behavior is unchanged and the estimate stays deterministic
and dependency-free (rescued from #70).

**Stale tracked bytecode** — `scripts/__pycache__/extract.cpython-313.pyc` was committed
alongside the EPUB-support change and has been tracked ever since, despite `.gitignore`
listing both `*.pyc` and `__pycache__/` (ignore rules do not untrack already-committed
files). The file was inert — its timestamp-based header records a 11,321-byte source while
`scripts/extract.py` is now 871 bytes, so Python always invalidated it and recompiled — but
committed bytecode is not reviewable in a diff. A regression test now fails if any `.pyc`
or `__pycache__/` path is tracked.
