# srdatatools

**srdatatools** is a local, open-source, single-user desktop application for
importing, merging, deduplicating, enriching, and exporting collections of
academic paper metadata from multiple sources.

It's built for researchers and students doing systematic reviews or
literature management who want a free, local alternative to juggling exports
from multiple databases by hand.

## Status: work in progress

This project is under active early development and is **not yet usable
end-to-end**. Phase 0 (foundation — schema, database, packaging, CI, contribution
basics) is complete; Phase 1 (import & storage) is in progress. There is no
release build yet, and the feature set described below is the target, not
the current state.

See [design_document.md](design_document.md) for the full architecture, data
model, and the phased feature to-do list that tracks current progress.

## What it will do

- Import bibliographic records from RIS, NBIB (PubMed), and CSV files
- Store everything in one local database so multiple source files can be
  combined without duplicate entries
- Deduplicate records across sources (e.g. the same paper appearing in both
  a PubMed and a Scopus export)
- Export the combined, cleaned collection back to RIS/CSV
- Enrich records with metadata from OpenAlex (abstracts, citation counts,
  open-access links, missing fields)
- Snowball references/citations of a paper to discover related work
- A GUI for import/export, dataset statistics, and a full activity log of
  every action taken on the data

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup details, code style, and
the PR process. `design_document.md` is the source of truth for scope and
architecture — please open an issue before starting on anything non-trivial.

## License

MIT — see [LICENSE](LICENSE).
