# PHANTOM tracking replay

`tracking_replay.py` validates and replays bounded JSONL snapshots through a
deterministic alignment/mapping oracle. Recording is opt-in and contains no
camera images. Each record carries HMD lifecycle data, Shoulder/Wrist source or
query time, receive time, uncertainty, validity/quality, grasp readiness/value,
Left Grip validity/value and frame id.
