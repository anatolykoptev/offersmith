# Third-party software

Offersmith is Apache-2.0 (see [LICENSE](LICENSE)). Its Python dependencies are in `pyproject.toml` and `uv.lock`. The optional OpenResume layer of the ATS check ([docs](docs/ats-check.md#the-openresume-layer-optional)) fetches the software below on the user's machine; none of it is stored in this repository or in the Python wheel.

| Software | Licence | How it is used |
|---|---|---|
| [OpenResume](https://github.com/xitanggg/open-resume) (xitanggg/open-resume), commit `4f8255a2c763479837f69f1dccf2a3338730cd79` | AGPL-3.0 (its `LICENSE`) | Fetched by `tools/openresume/install.sh` with `git fetch` of that commit. Its PDF parser (`src/app/lib/parse-resume-from-pdf`) is run unmodified, locally, by `tools/openresume/run.ts`, our own Apache-2.0 script that only imports it. It is not a network service and is not changed, so AGPL section 13 does not come into play. Anyone who redistributes a copy of OpenResume owes its source and licence. |
| [pdfjs-dist](https://github.com/mozilla/pdf.js) 3.7.107 (Mozilla) | Apache-2.0 | npm dependency of `tools/openresume`, the version in OpenResume's own lockfile. Affected by GHSA-wgrm-67xf-hhpq; mitigated by running Node with `--disallow-code-generation-from-strings` and by passing `isEvalSupported: false` to pdf.js. |
| [tsx](https://github.com/privatenumber/tsx) 4.23.15 | MIT | Runs the TypeScript runner. |
| [@reduxjs/toolkit](https://github.com/reduxjs/redux-toolkit) 1.9.5 | MIT | Imported by one OpenResume module; the version in its lockfile. |

The rest of the dependency tree is in `tools/openresume/package-lock.json`.
