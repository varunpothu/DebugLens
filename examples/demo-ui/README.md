# Demo UI fixture

A tiny, synthetic storefront designed to demonstrate DebugLens. It has no backend, tracking, external fonts, or third-party assets.

## Intentional defects

The default page contains three visual issues:

1. The primary button uses a width larger than its content container, which can cause horizontal overflow.
2. Supporting text uses a very light grey on white, producing weak contrast.
3. The action row does not wrap by default, making narrow layouts more fragile.

The fixed variant is the same page with a small CSS correction enabled through the `fixed=1` query parameter.

## Run locally

From the repository root:

~~~powershell
py -m http.server 8081 --directory examples/demo-ui
~~~

Open:

- Broken fixture: http://localhost:8081/
- Fixed fixture: http://localhost:8081/?fixed=1

Use a narrow viewport such as 390 x 844 and capture both pages. In a local-only environment, browser evidence can be enabled with:

~~~dotenv
BROWSER_ENABLED=true
BROWSER_ALLOWED_HOSTS=localhost
~~~

Restart the API and submit the exact local URL to the browser evidence endpoint. Keep this configuration local. Do not use localhost as an allow-list shortcut in a deployed environment; browser capture must run with network-level egress controls.

## Suggested issue report

"The primary action extends beyond the card on a narrow viewport. The supporting text is difficult to read. Please identify visible evidence, propose regression checks, and do not apply any changes automatically."

The fixture deliberately has no test that silently fixes the bug. Reviewers should inspect the proposed diagnosis and manually compare the broken and fixed versions.
