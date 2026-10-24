# PubMed papers with a Massachusetts affiliation, 2024

Saved 2026-10-18 for Hackachusetts.

PubMed records with a Massachusetts affiliation and a 2024 publication date. The live call returns 20 ids. data.csv has titles and journals for a larger saved slice of the same query.

Rows in data.csv: 60

Columns: pmid, title, journal, published, authors

How to use it

- Spreadsheets: open data.csv in Excel or Google Sheets.
- Fresh copy: run `python fetch.py` or `node fetch.js`. Both call the URL below and save the response.
- The preview on the Hackachusetts site is a few rows of this same table.

Direct request

https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=Massachusetts%5BAD%5D+AND+2024%5BPDAT%5D&retmax=20&retmode=json&tool=hackachusetts&email=hackachusetts@example.com

Check the source license before publishing a project.
