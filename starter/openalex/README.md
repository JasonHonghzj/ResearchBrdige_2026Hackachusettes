# Massachusetts research institutions

Saved 2026-10-18 for Hackachusetts.

Education institutions OpenAlex places in Massachusetts, ordered by works count. The live call returns the first 25. data.csv has the full saved list. No API key is included.

Rows in data.csv: 135

Columns: institution, city, works, cited_by

How to use it

- Spreadsheets: open data.csv in Excel or Google Sheets.
- Fresh copy: run `python fetch.py` or `node fetch.js`. Both call the URL below and save the response.
- The preview on the Hackachusetts site is a few rows of this same table.

Direct request

https://api.openalex.org/institutions?filter=geo.region:Massachusetts,type:education&sort=works_count:desc&per_page=25&select=display_name,works_count,cited_by_count,geo

Check the source license before publishing a project.
