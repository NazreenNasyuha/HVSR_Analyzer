# Example signals

Three ready-to-load example recordings in the formats the app understands.
All three were generated from the **same synthetic microtremor recording**
with a **known 2 Hz resonance**, so whichever file you load you should see a
clean H/V peak near **f0 ≈ 2 Hz** (A0 ≈ 4).

| File(s) | Format | What it is |
|---|---|---|
| `example.eqd` | `.eqd` raw | One file holding all three interleaved components (Z, N, E) at 500 Hz |
| `example_Z.mseed`, `example_N.mseed`, `example_E.mseed` | miniSEED | Three single-component files (vertical, north, east) at 500 Hz — select **all three** together in the app |
| `example.sg2` | SEG-2 | One file holding three traces; the components are detected automatically from each trace's NOTE field |

## How to load them

- **`.eqd` or `.sg2`**: Tab 1 → *Auto-assign files...* and pick the single file,
  or drop it into the **VERTICAL (Z)** slot. Tick **Swap N / E** only if the
  H/V curve looks wrong.
- **miniSEED**: Tab 1 → *Auto-assign files...* and select the three
  `example_*.mseed` files together (Z / N / E are matched by name).

## Regenerating

The files are produced by `scripts/make_examples.py`, which also validates
that every file loads and recovers f0 ≈ 2 Hz:

```
python scripts/make_examples.py
```

Output: `examples/example.eqd`, `examples/example_Z.mseed`,
`examples/example_N.mseed`, `examples/example_E.mseed`, `examples/example.sg2`.
