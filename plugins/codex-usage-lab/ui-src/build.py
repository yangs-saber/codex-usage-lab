"""Bundle the editable MCP App into the plugin's single-file UI resource."""
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
bundle = here / "bundle.js"
subprocess.run(
    [str(here / "node_modules/.bin/esbuild"), str(here / "meter.js"),
     "--bundle", "--format=iife", "--minify", f"--outfile={bundle}"],
    check=True,
)
html = (here / "meter-template.html").read_text().replace(
    "/*BUNDLE*/", bundle.read_text()
)
(here.parent / "meter.html").write_text(html)
bundle.unlink()
