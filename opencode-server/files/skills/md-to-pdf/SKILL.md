# md-to-pdf

Convert a Markdown document to PDF through the cluster Gotenberg service and return the bytes to the current session. Use when the owner asks for a PDF of a markdown file, letter, report, or work product.

## Engine

`http://gotenberg.gotenberg.svc:3000` — Gotenberg 8 (chromium variant), cluster-internal. The PDF arrives as the HTTP response body, so it lands directly in the session's shell with no ephemeral pod artifacts.

## Boundary

- **Never use this for house resume targets** (`targets/*.md`): raw-LaTeX headers do not survive Chromium; resume PDFs render only through the owner-run local `make` pipeline (see `agent-knowledge` career `pipeline.md` → "PDF generation and storage pathways").
- LaTeX-free markdown only: letters, summaries, work products, reference documents.

## Procedure (busybox-wget compatible)

1. Obtain the markdown into a file, e.g. `doc.md` (fetch via GitHub MCP and write, or generate in-session).

2. Build the multipart body. The route REQUIRES an `index.html` wrapper containing the Go template marker `{{ toHTML "doc.md" }}` exactly where the rendered markdown should appear:

```sh
B="Md$(date +%s)dM"
{
  printf '%s\r\n' "--$B"
  printf '%s\r\n' 'Content-Disposition: form-data; name="files"; filename="index.html"'
  printf '%s\r\n' 'Content-Type: text/html'
  printf '\r\n'
  printf '%s\n' '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><title>Document</title><style>body{font-family:Georgia,serif;margin:1in;color:#1a1a2e;line-height:1.5}h1,h2{border-bottom:2px solid #50fa7b;padding-bottom:4pt}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:6pt 10pt}code{background:#f4f4f8}</style></head><body>{{ toHTML "doc.md" }}</body></html>'
  printf '\r\n%s\r\n' "--$B"
  printf '%s\r\n' 'Content-Disposition: form-data; name="files"; filename="doc.md"'
  printf '%s\r\n' 'Content-Type: text/markdown'
  printf '\r\n'
  cat doc.md
  printf '\r\n%s--\r\n' "--$B"
} > mp.tmp
```

3. Convert — the response body IS the PDF:

```sh
wget --header "Content-Type: multipart/form-data; boundary=$B" \
  --post-file=mp.tmp -q -O out.pdf \
  "http://gotenberg.gotenberg.svc:3000/forms/chromium/convert/markdown"
```

4. Verify and persist: check the header (`head -c 8 out.pdf` must show `%PDF-`), then copy to `/home/opencode/<name>.pdf` (the OpenCode PVC) so the artifact survives pod restarts and is ready for upload to object storage when that pathway is available.

## Options worth knowing

- Page size/margins/scale: form fields `paperWidth`, `paperHeight`, `marginTop`… `landscape`, `scale`.
- `printBackground=true` when the wrapper uses background colors.
- Header/footer: additional `header.html`/`footer.html` files (each a full HTML document; page numbers via `<span class="pageNumber"></span>`).
- PDF/A: `pdfa=PDF/A-2b` form field.

Full form-field reference: gotenberg.dev → "Convert Markdown to PDF".

## Failure modes (verified)

- `400 … index.html is required` — wrapper file missing or not named `index.html`.
- Empty ~1KB PDF — wrapper lacks the `{{ toHTML "doc.md" }}` marker (filename must match the uploaded md filename).
- `500 … chrome_crashpad_handler` — do not "fix" by weakening the security context; the deployed env already sets writable `HOME`/`XDG_*_HOME`. If it recurs, check the workload env before changing anything else.

Base directory for this skill: /home/opencode/.config/opencode/skills/md-to-pdf
