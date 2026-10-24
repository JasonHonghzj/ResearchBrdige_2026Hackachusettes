// Save a fresh copy of this Hackachusetts starter source.
// Run with: node fetch.js
const fs = require("node:fs/promises");

const url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=Massachusetts%5BAD%5D+AND+2024%5BPDAT%5D&retmax=20&retmode=json&tool=hackachusetts&email=hackachusetts@example.com";

async function main() {
  const response = await fetch(url, { headers: { "User-Agent": "HackachusettsKit" } });
  if (!response.ok) throw new Error("Request failed: " + response.status);
  const bytes = Buffer.from(await response.arrayBuffer());
  const type = response.headers.get("content-type") || "";
  let name = "fresh.json";
  if (url.includes(".csv") || type.includes("csv")) name = "fresh.csv";
  if (url.endsWith(".txt")) name = "fresh.txt";
  await fs.writeFile(name, bytes);
  console.log("wrote " + name + " (" + bytes.length + " bytes)");
}

main();
