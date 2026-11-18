"""Otto's research side (phase 5c): from published advisories to signed test packs.

This package is a build step run on our own machine (in production it would run at Isogeny Labs). It reads the
dated advisory snapshot under research/snapshot/, asks Claude to read each advisory, design a test and propose a
fix (recorded answers by default, live with --live and a key), tries every design and every fix on public copies
through Evidence Lab's own lock, run and review path, records all of it in an Otto lab under research/lab/ with
Adam's harness, and signs the test packs under research/packs/.

The app never imports this package: only a signed pack crosses from research to the customer. Nothing here decides
a result of a test (the reviewer does), and no decision about a trial is made here (Otto's harness judges it against
thresholds frozen before the first run).
"""
