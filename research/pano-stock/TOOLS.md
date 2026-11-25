# Tools and offline tests

Python standard library, Linux container. Run from this research directory:
```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest discover -s tests -v
```

- inventory.py and lan_discover.py: authorized private subnet inventory/discovery; results contain private identities, stdout only. pano_discovery.py: identity decoder and collector.
- config_read.py, framing.py, stream_status.py: bounded configuration and stream primitives.
- batch_reader.py and sequential_image.py: ordered acquisition algorithm used in original experiment, adapted to explicit private device selection and a single binary with checkpoint. No programming mode. The generalized source is not physically qualified yet.
- perf_model.py: strict response parser and illustrative throughput model.
- flash_audit.py: offline comparison of two complete raw images, region and sector summaries. No device access.

Keep inventory and binary output outside the checkout, owner-only. Do not run concurrent clients. Select the target by verified physical identity; do not rely on IP alone. Candidate requires explicit private identity record, authorized subnet and owner backup confirmation. On interrupted transfer preserve existing checkpoint, confirm identity and idle status before resuming. No automatic retry or reset. The original reference acquisition and its source are separately preserved privately. Original physical qualification does not establish performance or correctness on other boards, or on generalized code. Do not perform restoration without separately qualified recovery.

Tests use synthetic identities and mock transport, never the actual board; real captures remain private.
