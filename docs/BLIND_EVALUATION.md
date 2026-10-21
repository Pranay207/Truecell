# Independent blind evaluation

Truecell separates extraction from scoring so the extractor never needs access to held-out truth.

## Roles

1. The evaluator collects public, dummy or authorized documents and records their SHA-256 hashes in a version-1 manifest.
2. The evaluator keeps the truth directory private during extraction.
3. The developer freezes the Truecell revision and runs only the extraction command.
4. The evaluator supplies truth after the run and scores the saved audit files without rerunning extraction.

Do not use personal, restricted or confidential documents. Record source, licence, category and language outside the truth files.

## Extract without truth

```powershell
.\.venv\Scripts\python.exe scripts\blind_benchmark.py extract `
  --manifest evaluation-pack\manifest.json `
  --inputs evaluation-pack\inputs `
  --outputs evaluation-run
```

This writes source-bound audit JSON, Excel workbooks and `run.json`. `run.json` records that truth was unavailable during extraction.

## Score the saved run

```powershell
.\.venv\Scripts\python.exe scripts\blind_benchmark.py score `
  --manifest evaluation-pack\manifest.json `
  --outputs evaluation-run `
  --truth evaluation-pack\truth
```

Scoring reads the saved audits. It refuses a changed manifest, mismatched source hash, unsafe path or incomplete case. A pass requires exact cells, headers and shapes plus every annotated injected error.

Use `eval/blind_manifest.example.json` as a schema example and replace its zero hash. Report results only for the frozen pack; never present them as universal accuracy.
