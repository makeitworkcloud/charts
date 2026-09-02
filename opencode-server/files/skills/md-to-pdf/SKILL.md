# md-to-pdf

Convert a Markdown document to PDF through the cluster Gotenberg service and return the bytes to the current session. Use when the owner asks for a PDF of a resume, letter, report, or work product.

## Engine

`http://gotenberg.gotenberg.svc:3000` — Gotenberg 8 (Chromium variant), cluster-internal. The PDF arrives as the HTTP response body, so it lands directly in the session shell with no renderer-pod artifact to retrieve.

## Resume rendering boundary — preferred method

**The preferred resume-PDF method is server-side Gotenberg rendering from a LaTeX-free Markdown body and an HTML/CSS wrapper.** The career workspace remains authoritative for verified facts, target wording, and source lifecycle; rendering does not authorize new facts or submission.

- Never send a raw-LaTeX `targets/*.md` source directly to Chromium. Create a derived, LaTeX-free Markdown body that contains only the resume sections and verified bullets.
- Provide an `index.html` wrapper that lays out the header, typography, page breaks, and the required `{{ toHTML "<body-file>.md" }}` marker.
- Embed the canonical circular headshot as a `data:image/png;base64,...` URI in the wrapper. Do not rely on a temporary authenticated source URL and do not add the image as a separate multipart file; the latter has returned HTTP 400 in the deployed service.
- Keep the PDF to two pages. Use CSS page-break controls before role headings when necessary, then verify the output mechanically and visually.
- This replaces the former local-only rendering preference. The local Pandoc/XeLaTeX Makefile remains a legacy fallback for an owner who explicitly requests it, not the default path.

## Procedure (BusyBox-wget compatible)

1. Read the current career workspace target and facts guidance through GitHub MCP. Prepare the LaTeX-free body in a temporary file such as `resume.md`; it must not introduce facts or leave placeholders.

2. Prepare `index.html`. It must contain the Go template marker `{{ toHTML "resume.md" }}` exactly where the rendered Markdown should appear. For resumes, include explicit HTML/CSS header and section styles rather than relying on browser defaults. The headshot source must be the inline data URI described above.

3. Build the multipart body. The route requires the wrapper file to be named `index.html`:

```sh
B="Md$(date +%s)dM"
{
  printf '%s\r\n' "--$B"
  printf '%s\r\n' 'Content-Disposition: form-data; name="files"; filename="index.html"'
  printf '%s\r\n' 'Content-Type: text/html'
  printf '\r\n'
  cat index.html
  printf '\r\n%s\r\n' "--$B"
  printf '%s\r\n' 'Content-Disposition: form-data; name="files"; filename="resume.md"'
  printf '%s\r\n' 'Content-Type: text/markdown'
  printf '\r\n'
  cat resume.md
  printf '\r\n%s--\r\n' "--$B"
} > mp.tmp
```

4. Convert — the response body is the PDF:

```sh
wget --header "Content-Type: multipart/form-data; boundary=$B" \
  --post-file=mp.tmp -q -O out.pdf \
  "http://gotenberg.gotenberg.svc:3000/forms/chromium/convert/markdown"
```

5. Verify and persist:

- `head -c 8 out.pdf` must show `%PDF-`.
- Verify two pages or fewer and inspect the rendered first page: the circular headshot must be present in the top-right header, with no placeholder or remote-image failure.
- Persist an artifact that must survive a pod restart to `/artifacts/<name>.pdf`. This PVC is isolated from the OpenCode home and is the only filesystem visible to the upload helper.
- Do not claim S3 publication or give a download URL until the object upload and `HeadObject` verification have succeeded. The current agent-pipe transport uses the separate, credential-free curl uploader Pod; follow `s3-presigned-file-delivery` for the confirmation-gated upload procedure.

## Options worth knowing

- Page size/margins/scale: form fields `paperWidth`, `paperHeight`, `marginTop`… `landscape`, `scale`.
- `printBackground=true` when the wrapper uses background colors.
- Header/footer: additional `header.html`/`footer.html` files (each a full HTML document; page numbers via `<span class="pageNumber"></span>`).
- PDF/A: `pdfa=PDF/A-2b` form field.

Full form-field reference: [Gotenberg Convert Markdown to PDF](https://gotenberg.dev/docs/routes#convert-into-pdf).

## Failure modes (verified)

- `400 … index.html is required` — wrapper file missing or not named `index.html`.
- Empty ~1KB PDF — wrapper lacks the `{{ toHTML "resume.md" }}` marker (filename must match the uploaded Markdown filename).
- `400` when attaching `profile-circle.png` as an additional multipart input — use the data URI in the wrapper instead.
- `500 … chrome_crashpad_handler` — do not weaken the security context; the deployed environment already sets writable `HOME`/`XDG_*_HOME`. If it recurs, inspect workload environment before changing anything else.

Base directory for this skill: /home/opencode/.config/opencode/skills/md-to-pdf
