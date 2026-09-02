---
name: pull-request-template
description: Use before opening any pull request through the API, to fetch and apply the repository's pull-request template manually.
---

# Pull-request template application

Pull request templates are applied only by the GitHub web UI; API-created
pull requests bypass them, so apply the template manually.

1. Fetch the template with `github_get_file_contents` in this order, stopping
   at the first hit: the repository's `.github/PULL_REQUEST_TEMPLATE.md`, then
   root and `docs/` variants (filenames are case-insensitive), then the
   organization default at `makeitworkcloud/.github`
   (`.github/PULL_REQUEST_TEMPLATE.md`).
2. Use the fetched template as the pull request body skeleton: preserve every
   heading, fill each section, replace placeholders such as `Fixes #`, and
   remove HTML comments.
3. If no template exists in any location, state that in the pull request body
   instead of writing a free-form description.
