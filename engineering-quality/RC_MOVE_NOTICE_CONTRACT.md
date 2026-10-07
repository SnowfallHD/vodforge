# Move notice test contract

Commit3613d2c intentionally replaces older per-item Move wording with the shared all-selection summary. The aggregate RC2 run completed476Qt component passes and found two older notice tests still asserting the removed strings. Runtime Move behavior and wording are unchanged here.

These tests now verify that every selected item is counted, supported media remains eligible, hierarchy-root-unknown items are described as unsupported layouts and kept, and neither category is falsely described as inaccessible. Reviewed plan reasons remain intact, no worker starts during review, and no destination is created. Preserve RC2 failures and artifact receipts; rerun aggregate against the new clean test-source commit.
