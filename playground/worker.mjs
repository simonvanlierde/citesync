const runtimeURL = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
let engine;
function load() {
  if (!engine) {
    engine = (async () => {
      const [python, { manifest, wheels }] = await Promise.all([
        import(`${runtimeURL}pyodide.mjs`).then(({ loadPyodide }) => loadPyodide({ indexURL: runtimeURL })),
        (async () => {
          const response = await fetch("./runtime.json");
          if (!response.ok) throw new Error("The converter build is missing. Reload the page or try again later.");
          const manifest = await response.json();
          const wheels = await Promise.all(
            manifest.wheels.map(async ({ name, sha256 }) => {
              const wheel = await fetch(`./wheels/${name}?sha256=${sha256}`);
              if (!wheel.ok) throw new Error("A converter package could not be downloaded.");
              const content = await wheel.arrayBuffer();
              const digest = await crypto.subtle.digest("SHA-256", content);
              const actual = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
              if (actual !== sha256)
                throw new Error("Converter files changed during loading. Retry the current build.");
              return { name, content };
            }),
          );
          return { manifest, wheels };
        })(),
      ]);
      self.postMessage({ type: "setup" });
      for (const { name, content } of wheels) python.FS.writeFile(`/tmp/${name}`, new Uint8Array(content));
      python.globals.set("wheel_names_json", JSON.stringify(manifest.wheels.map(({ name }) => name)));
      await python.runPythonAsync(`
import json, zipfile, sys
from pathlib import Path
site = Path('/tmp/citesync-packages')
site.mkdir(exist_ok=True)
for name in json.loads(wheel_names_json):
    with zipfile.ZipFile('/tmp/' + name) as wheel:
        wheel.extractall(site)
sys.path.insert(0, str(site))
from citesync.playground import generate
`);
      self.postMessage({ type: "ready", version: manifest.version });
      return python;
    })();
  }
  return engine;
}
self.onmessage = async ({ data }) => {
  let python;
  try {
    python = await load();
  } catch {
    engine = null;
    self.postMessage({
      id: data.id,
      message: "The converter could not load. Your input is still here. Check your connection, then retry.",
      type: "load-error",
    });
    return;
  }
  if (data.type === "warmup") return;
  try {
    python.globals.set("request_json", JSON.stringify(data.payload));
    const response = python.runPython(`
try:
    response_json = json.dumps({'result': generate(json.loads(request_json))}, ensure_ascii=False)
except Exception as error:
    response_json = json.dumps({'error': str(error)}, ensure_ascii=False)
response_json
`);
    const result = JSON.parse(response);
    self.postMessage({ id: data.id, type: result.error ? "input-error" : "result", ...result });
  } catch {
    self.postMessage({
      error: "Conversion could not finish. Try a smaller file or check the metadata.",
      id: data.id,
      type: "input-error",
    });
  }
};
