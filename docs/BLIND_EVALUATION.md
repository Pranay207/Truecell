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

This writes source-bound audit JSON, Excel workbooks and `run.json`. The command prints the SHA-256 of `run.json`. The evaluator must copy that digest to a separate record before truth is supplied; a digest kept only inside the output folder is not an independent seal. The run metadata records the evaluator-withheld protocol as an auditable declaration, not as cryptographic proof of what the extraction host could access.

## Score the saved run

```powershell
.\.venv\Scripts\python.exe scripts\blind_benchmark.py score `
  --manifest evaluation-pack\manifest.json `
  --outputs evaluation-run `
  --truth evaluation-pack\truth `
  --run-sha256 <digest-recorded-by-the-evaluator>
```

Scoring reads the saved audits. It refuses a changed `run.json` seal, extraction source fingerprint, manifest, audit, workbook, source hash, OCR-language route, unsafe path or incomplete case. Each case records a runtime signature covering the source, extraction code/options, installed OCR packages, bundled ONNX assets, Tesseract version and the requested installed language assets. It also verifies every `Data N` workbook value, cell type and number format against a fresh export from the frozen audit before scoring. A pass requires exact cells, headers and shapes plus every annotated injected error.

The input manifest uses schema version 1; the generated `run.json` uses run-metadata schema version 2. These numbers version different records and are expected to differ. Use `eval/blind_manifest.example.json` as the manifest example and replace its zero hash. Report results only for the frozen pack; never present them as universal accuracy.
