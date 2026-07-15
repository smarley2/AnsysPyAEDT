# Deferred KDM powder-core families

The following KDM families are excluded from the current catalog import by the
documented scope decision of 2026-07-15:

- KPH-HP — Super Sendust G3 — `https://www.kdm-mag.com/products/details-datasheets-1581.html`
- KPH-HT — Super Sendust G4 — `https://www.kdm-mag.com/products/details-datasheets-1584.html`
- KSF-HP — Low Loss Si-Fe G3 — `https://www.kdm-mag.com/products/details-datasheets-1586.html`
- KSF-FC — High DCBias Si-Fe G3 — `https://www.kdm-mag.com/products/details-datasheets-1588.html`
- KSF-HT — Si-Fe G4 — `https://www.kdm-mag.com/products/details-datasheets-1590.html`
- KH-HP — High Flux G3 — `https://www.kdm-mag.com/products/details-datasheets-1592.html`
- KH-HT — High Flux G4 — `https://www.kdm-mag.com/products/details-datasheets-1594.html`

Each official product page is accessible, but its linked datasheet page contains
no product table, downloadable datasheet, or part numbers. These families must
remain deferred until KDM publishes authoritative dimensional and magnetic data.
They must not be inferred from another family.

KDM MPP (`KM`) is imported separately by `tools/scrape_kdm_mpp.py` into
`catalog/cores/kdm-mpp.yaml`.
