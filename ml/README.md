# ml — Predictive Maintenance / Fault Detection

This is where BAP's actual research deliverable lives: a deep-learning
model for predictive maintenance of the UAV's motors and the gripper,
fused across both sensor sources. Not started yet — this is a scaffold,
not a working pipeline.

## Data sources

- **Gripper**: [`../gripper/data/`](../gripper/data/) — Tier-1 (commanded-angle)
  trial CSVs from the ArmBot logger, per-object/scenario/condition. See
  [`../gripper/README.md`](../gripper/README.md) §6 for the schema.
- **UAV motors**: not yet instrumented/logged from this workspace — PX4
  exposes motor/ESC telemetry over `/fmu/out/*` (see [`../Docs/setup.md`](../Docs/setup.md)),
  but nothing here captures or stores it as a dataset yet.

## Layout

```
ml/
├── data/         # Prepared/derived datasets (features, splits) — raw trial
│                 # data stays in gripper/data/, this is downstream of it
├── notebooks/    # Exploration, feature engineering, model iteration
├── models/       # Trained model artifacts / checkpoints
├── requirements.txt   # own venv, separate from gripper/'s — see gripper/README.md §2
└── README.md
```

## Open questions (not yet decided)

- Health-indicator / feature design for both motor and gripper streams
  (time-domain stats — RMS, kurtosis — over a sliding window is the
  leading candidate).
- Real vs. synthetic fault data — the gripper logger currently only
  captures **normal-condition** trials (`condition_label=normal`); a
  labeled fault dataset (real induced faults, and/or simulated
  degradation) is still an open problem, not solved by anything in this
  repo yet.
- Model architecture and how motor + gripper streams actually get fused.

Fill this in as those decisions get made — don't let this file drift out
of sync with what's actually implemented.
