# NR2301 WebUI route crawler v4

This helper is a research-only, read-only physical-router inventory crawler.

It was added after the source-driven v3 crawl on 2026-09-14 captured 13 complete browser states and then blocked indefinitely while `page.content()` was called for `engineering.html`. The source file for that route had already been saved, confirming the hang was in Playwright DOM capture rather than route discovery.

v4 hardens the crawl by:

- removing `page.content()` from the capture path;
- using timeout-bounded locator text/HTML reads and screenshot capture;
- using a fresh Playwright page per route;
- setting bounded default and navigation timeouts;
- keeping source-driven recursive route discovery from `openPage(...)`, ordinary HTML links, window-open calls and page-specific JavaScript;
- writing a checkpoint after every route;
- printing a progress line after every route;
- catching `KeyboardInterrupt` and finalizing a partial evidence ZIP instead of losing the run;
- retaining the existing mutation-like request and USB/management-mode mutation blocks.

Raw evidence may contain local router state and must remain private. The generated `webui_routes_v4_*/` directories and ZIPs are covered by the repository's existing WebUI evidence ignore patterns.
