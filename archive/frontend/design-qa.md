# Design QA - Ngeebula frontend draft

## Evidence

- Source visual truth: `C:\Users\m4rcw\.codex\generated_images\01a0aa2f-8343-7bc1-b89c-4d8c5d39c61d\exec-99ab1115-4c9d-4053-a351-2f66654c23fa.png`
- Source pixels: 1488 x 1056.
- Implementation URL: `http://127.0.0.1:8501/`
- Implementation screenshot: Codex in-app Browser, browser 1 / tab 3 inline capture. The browser integration did not expose a filesystem path for the capture.
- Browser viewport: 1280 x 720 CSS pixels at device scale factor 1.
- State: Operations, demo data, all lines, all statuses, all priorities.
- Density normalization: the source was judged at proportional 1280px-wide scale; the implementation's full-page scroll was also inspected so below-fold table content was not mistaken for missing content.

## Full-view comparison

The implementation preserves the selected concept's primary composition: dark navy control-room shell, compact left navigation, schedule-first main region, large Gantt timeline, right-side AI recommendation, blue review action, and scheduled-jobs table. At the shorter browser viewport the table begins below the fold, as expected; it is present and readable when scrolled.

## Focused region comparison

- Gantt: overnight 12:30 AM-5:00 AM window, track rows, status colours, labels, and 30-minute buffers are legible and follow the source hierarchy.
- Recommendation panel: conflict title, affected work, suggested action, impact summary, and primary review action match the source structure.
- Navigation and filters: hierarchy, selected state, contrast, and compact sizing are consistent with the source direction.
- Job table: all required backend fields are visible and the table remains usable at the tested viewport.

## Required fidelity surfaces

- Fonts and typography: passed. Inter/Segoe UI fallbacks reproduce the modern operational sans-serif hierarchy with readable body sizes and weights.
- Spacing and layout rhythm: passed. Major-region proportions, gaps, borders, radii, and dense dashboard rhythm match the source. The shorter test viewport causes normal vertical scrolling only.
- Colours and visual tokens: passed. Navy surfaces and semantic green/red/orange/blue/charcoal status colours match the selected direction and preserve accessible contrast.
- Image quality and asset fidelity: passed. The selected design contains no custom raster imagery or logo assets. Plotly renders the data visualization sharply; no placeholder imagery or handcrafted SVG assets were introduced.
- Copy and content: passed. Product title, overnight engineering window, realistic MRT maintenance jobs, conflict explanation, buffers, engineers, priorities, and status language align with the brief and backend contract.

## Interaction and runtime checks

- MRT line filter: tested with CCL and restored to All lines.
- Alerts navigation: passed.
- Audit log navigation: passed.
- Review proposal in demo mode: passed with visible success feedback.
- Live-backend failure path: passed; the app clearly switches to demo data.
- Python compilation and demo-data assertions: passed.
- Browser/runtime errors: none observed after the final compatibility fixes.

## Findings

No actionable P0, P1, or P2 design differences remain.

## Follow-up polish

- [P3] Add an icon library only if the team later wants sidebar icons closer to the concept image.
- [P3] Add richer MRT line grouping when the backend provides a larger set of tracks and stations.

## Comparison history

- Initial browser pass: core layout and interactions rendered correctly. Streamlit and Pandas emitted forward-compatibility warnings.
- Fixes made: replaced deprecated width arguments and normalized timeline-bound arithmetic.
- Post-fix evidence: the dashboard re-rendered without new terminal warnings; filters, secondary pages, and proposal review were re-tested.

## Implementation checklist

- [x] Selected design direction implemented.
- [x] FastAPI client and graceful fallback included.
- [x] Plotly Gantt, buffers, conflict detection, recommendation, and job table included.
- [x] Primary interactions tested in the browser.
- [x] All repository changes confined to `frontend/`.

final result: passed
