## Archify v3.2.0

Create a conclusion-first one-page answer from Markdown, with cited sources, interactive diagrams and browser exports.

### Added

- **One-page answers (explainer) (#993).** Ask your agent to answer as a page and Archify builds a conclusion-first explainer from a Markdown draft. Each panel answers one question, using prose, tables, steps, checklists, charts, code and validated native diagrams.
  - **Authoring and delivery:** `finalize explainer` validates, delivers atomically and checks the page. Charts come from a Mermaid fence or a CSV/JSON file next to the draft. Repository excerpts are read from the pinned commit. `patch explainer` replaces one panel by ID.
  - **Reading:**
    - Steps sit beside the diagram they walk through, and you can step through them.
    - Text and diagram nodes highlight each other.
    - Clicking a node opens the full Viewer focused on it.
    - Citations and source-linked nodes open source cards.
    - Each panel or selected passage produces a follow-up question that targets that panel.
  - **Sharing:** the page ships in four styles (clean, editorial, product, Swiss) with light and dark themes, and exports a PNG, WebP or JPG long image or prints to PDF.
  - **Examples:** four live pages in `docs/cases/explainer/`.
  - **Credit:** the one-page document direction of #942 by @goatliamia shaped this work.
  - **Acknowledgment:** thanks to @QingYunA for the early one-page diagram-and-explanation proposal and demo prototype.

### Fixed

- **Explainer pages no longer carry local paths.** The draft embedded in a page names its source and data files relative to the page, so a shared page does not reveal the author's directories. `patch explainer` resolves them against the page again.

- **Explainer long images keep the page's style and theme.** A PNG, WebP or JPG export of a dark page, or of the editorial, product or Swiss style, came out in the light clean style, because the page is drawn inside an SVG where its `<html>` is not `:root`. The export now selects the page root by its own attribute.

- **Blank chart data is an error, not zero.** An empty CSV cell, a JSON `null` or a missing field in a charted column no longer becomes a zero bar. Finalize names the column and row instead.

- **Workflow migration semantic contracts (#497).** Layout planning no longer checks full-topology requirements against a temporary graph with routed edges removed. Migrated documents retain their authored contracts and must pass complete validation before publication.

- **Timeline 时区刻度（#926）。** 刻度按显示时区在各真实时刻的 UTC 偏移对齐，修复跨夏令时后日刻度漂移到 01:00／23:00、半小时跳变后小时刻度漂移的问题。回拨的重复时刻保持独立，跳过的小时或日期不生成虚构刻度；事件时间、标签精度、时间轴比例与断轴规则保持不变。

### Changed
- **Reader controls and node index.** Compact bottom index rows keep descriptions below titles; menu and roving keyboard navigation respect modifier keys.
- **Update notices.** Available updates include a release summary and an offer to help update. Network failures remain non-blocking.
- **Website and portability.** The bilingual homepage and gallery introduce one-page answers while retaining guides and source-backed cases. Browser discovery, Windows command paths, source-directory whitespace and temporary-worktree cleanup receive focused fixes.

### Distribution
- Download `archify.zip` below. Stable update notifications are published separately after the archive has been verified.
- The separately versioned DSH plugin is not republished with this release; maintainers must select a pinned source and complete its host/package acceptance in a separate follow-up.

**Full changelog:** https://github.com/tt-a1i/archify/compare/v3.1.0...v3.2.0
