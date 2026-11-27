# Check a Python release against its citations

Run these checks before uploading a wheel and source distribution. Use the built files so the check can catch a stale version or licence that a check of the checkout alone could miss.

## Build the artifacts and copy their metadata

The example uses CiteSync 0.7.0. Start in the release checkout with [CiteSync installed](getting-started.md) and `uv` available. For another project, substitute its artifact and archive member names and copy the citation files it uses.

```sh
release_check=$(mktemp -d) &&
  uv build --out-dir "$release_check/dist" &&
  cp CITATION.cff codemeta.json "$release_check/" &&
  python3 - "$release_check" <<'PY'
import sys
import tarfile
import zipfile
from pathlib import Path

root = Path(sys.argv[1])
with zipfile.ZipFile(root / "dist/citesync-0.7.0-py3-none-any.whl") as wheel:
    header = wheel.read("citesync-0.7.0.dist-info/METADATA")
    (root / "METADATA").write_bytes(header)
    pin = wheel.read("citesync/MAPPING_SOURCE").decode().splitlines()
    print(next(line for line in pin if line.startswith("tag ")))

with tarfile.open(root / "dist/citesync-0.7.0.tar.gz", "r:gz") as sdist:
    header = sdist.extractfile("citesync-0.7.0/PKG-INFO").read()
    (root / "PKG-INFO").write_bytes(header)
PY
```

The command copies just the two metadata members. It also prints the mapping tag in the wheel so you can record which mapping the release ships.

## Require fields and check both artifacts

Save this configuration as `citesync.toml` in the temporary directory. For a project that ships `.zenodo.json`, copy it there and add its own requirements.

```sh
cat >"$release_check/citesync.toml" <<'TOML' &&
[required-fields]
"CITATION.cff" = ["name", "version", "author", "license"]
"codemeta.json" = ["name", "version", "author", "license"]
"METADATA" = ["name", "version", "author", "license"]
"PKG-INFO" = ["name", "version", "author", "license"]
TOML
  citesync check --root "$release_check" --source METADATA &&
  citesync check --root "$release_check" --source PKG-INFO
```

Each command compares the citation files with one artifact. In CI, run this block in a step that must pass before upload.

| Field | Wheel and source distribution | Citation files |
| --- | --- | --- |
| Name and version | `Name` and `Version` | Title or name and version |
| Authors | Author headers | Structured author records |
| Licence | SPDX `License-Expression` | Licence field or URL |
| DOI and release date | The importer supplies neither | Check them separately if the release requires them |

The CiteSync candidate had identical metadata in both artifacts. Both checks reported zero errors and warnings. Its checkout supplies CFF and CodeMeta and has no `.zenodo.json`. Add `-v` to either check to see skipped fields. See the [Python distribution reader](formats.md#python-distribution-metadata) and [required fields](config.md#require-values-in-selected-files) for the supported values.

## Reproduce and repair a stale citation version

Change the version to `0.6.0` in the **temporary copy** of `CITATION.cff`. Run the wheel check again.

```sh
citesync check --root "$release_check" --source METADATA
```

The check exits with status 1 and includes this finding.

```text
error[version-mismatch] version: '0.6.0', METADATA has '0.7.0'
```

Restore the file from the checked-out release and run both checks again.

```sh
cp CITATION.cff "$release_check/CITATION.cff" &&
  citesync check --root "$release_check" --source METADATA &&
  citesync check --root "$release_check" --source PKG-INFO
```

Both checks now pass. When a real release fails, correct the file with the wrong version. If the artifact was wrong, rebuild it and extract its metadata again before running the checks.
