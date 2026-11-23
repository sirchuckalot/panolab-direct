# Local tests

Run in the laptop's development or dedicated local test container:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

The unit tests exercise source safety and the external five-tool MCP
contract; they do not mean the licensed vendor ISE 14.7 build or
physical FPGA programming passed. `fixtures/ise_counter` is a
standalone input for later explicitly authorized vendor acceptance;
do not flash any resulting generic bitstream.
