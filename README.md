# Irona for KiCad

Four small KiCad plugins (and a matching CLI) for checking and documenting a board you designed:

| Plugin | What it does |
| --- | --- |
| **Irona Simulator** | DC IR drop and current density per net, a lumped thermal hotspot estimate, and microstrip impedance per trace. You enter load currents and part dissipation; they are remembered per project. |
| **Irona Rule Check** | Design-rule check of the board (clearances, drills, annular rings, edge clearance, unconnected items) and electrical-rule check of the schematic. |
| **Irona Design Review** | SI/PI and IPC-2221/2222/2223/6012 review, plus a circuit review (power rails, regulators, EMC pre-compliance, JLCPCB/PCBWay DFM) from the vendored [kicad-happy](https://github.com/aklofas/kicad-happy) analyzers. |
| **Irona Docs** | Design report PDF, schematic PDF, Gerbers + drill, BOM and placement CSVs, a fab ZIP and an index page, in `<project>/irona-out/docs/`. |

The dialogs use the [Dracula](https://draculatheme.com) palette, as do the generated index page and the report's headings.

## Install

```bash
python3 install_kicad_plugins.py
```

This copies the four plugins into KiCad's user plugin folder for each installed KiCad 9/10 (Flatpak or native) and points them at this checkout. It also removes the old single "Irona Hardware Engineering Studio" plugin. Restart the PCB editor, then use the toolbar buttons or **Tools → External Plugins**. `--dry-run` shows what would change; `--uninstall` removes everything.

The plugins analyse the files on disk, so save the board first.

## CLI

```bash
python3 -m irona sim    projects/buck_12v_3v3 --current VOUT_3V3=2 --power U1=0.35 --save --check
python3 -m irona check  projects/buck_12v_3v3 --check
python3 -m irona review projects/buck_12v_3v3
python3 -m irona docs   projects/buck_12v_3v3
```

`sim` reuses the inputs saved in `<project>/irona-sim.json` (by `--save` or the Simulator plugin) when none are given.

## How the numbers are computed

- **Simulation** is closed-form, straight from the `.kicad_pcb`: R = ρL/(W·t) over power-width segments (≥ 0.5 mm), J = I/(W·t), a natural-convection lumped thermal model over the Edge.Cuts area with a 1.35 hotspot factor, and the IPC-2141 surface microstrip formula (1.5 mm FR-4, 1 oz). There is no FEM solver involved; treat results as first-order estimates.
- **Docs** uses `kicad-cli` for Gerbers, drill and the schematic PDF (found on `PATH`, inside KiCad's Flatpak, or via `flatpak run`). Without it those outputs are listed as skipped; nothing is faked.
- Some SI/PI heuristics (hot-loop, FB vs SW spacing) look for buck-converter net names like `SW_NODE` and `FB` and are skipped when those nets do not exist.

## Layout

```
irona/                  core library (standard library only)
  simulation.py         BoardSimulator
  drc.py, erc.py        rule checks
  sipi_review.py        SI/PI + IPC review
  circuit_review.py     kicad-happy wrapper; happy/ is the vendored analyzer
  report_pdf.py         dependency-free PDF report
  docs.py               kicad-cli exports, BOM/positions, fab zip, index page
  kicad_ui.py           shared plugin registration + Dracula wx dialog
  theme.py              Dracula palette
  cli.py                python -m irona …
plugins/irona_*/        one KiCad action plugin each (dialog.py + icon)
projects/               sample projects used by the tests
tests/                  python -m unittest discover -s tests -t .
config/kibot.yaml       optional KiBot outputs used in CI
```

## Screenshots

| Simulator | Design Review |
| --- | --- |
| ![Simulator](docs/screenshots/simulator.png) | ![Design Review](docs/screenshots/design_review.png) |
