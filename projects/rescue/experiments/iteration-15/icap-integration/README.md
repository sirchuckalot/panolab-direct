# Spartan-6 ICAP launch interlock simulation

Run `./run_tests.sh` with Icarus Verilog. The testbench checks the 14 words at
the ICAP primitive pins, including the byte-wise bit reversal. It uses the
existing sibling simulation stub, which has no configuration engine.

The local transmitter has one ICAP primitive. Its compile-time synthetic byte
addresses are APP A `0x123456`, APP B `0x654321`, and Rescue `0x000000`, with
synthetic read opcode `0x03`. The interlock latches only the APP A/B bit on
acceptance. Rescue is a fixed fallback field in both packets and cannot be
selected as the primary image. Protect the Rescue flash region from writes or
erases through the trusted platform's flash protection. The simulation models
the packet fields only.

## Trusted firmware and arbitration contract

- Bring all inputs into the ICAP clock domain with suitable synchronization
  and coherent transfer of the selection and its qualifiers. Use an ICAP clock
  at or below the qualified rate for the device and operating conditions. The
  testbench clock is 10 MHz for simulation and does not establish that rate.
- Trusted firmware must durably commit the pending trial record and verify the
  selected image before asserting `durable_trial_valid` and `image_verified`.
  These attestations must refer to the same selected slot and image and remain
  valid through acceptance. Keep the verified image protected from modification.
  Firmware owns trial recovery, rollback policy, and any decision to try again.
- Assert `trusted_arm` separately from `start`. Idle SPI and valid
  prerequisites cause the interlock to raise its registered
  `spi_lock_request`. The trusted SPI arbiter must drain outstanding work,
  exclude all other SPI users, and assert `spi_lock_grant` only for an active
  request with exclusive ownership. Preserve that ownership for as long as the
  request stays asserted, including after `done`.
- Drive `start` low for at least one sampled clock while armed, then drive
  it high with all prerequisites and the request and grant present. An early
  edge is consumed even if the prerequisites later become valid while
  `start` stays high. A fresh edge is required. If a prerequisite becomes
  invalid before acceptance, the request drops on the next sampling edge.
- `accepted` latches selection and holds the SPI request until reset. The
  transmitter starts on the following rising edge and completes one packet.
  `done` indicates that the last word was driven. It does not confirm
  reconfiguration, fallback, or a successful trial.

## Reset

Assert reset across a rising clock edge to clear the interlock, release its
SPI request, and clear transmission state. Reset also disables ICAP CE while
asserted. A start held high across reset cannot launch. After reset, a new
armed low-to-high start sequence must qualify.

Once transmission begins, reset can truncate future writes. Words already
sampled by ICAP remain outside the interlock's control, and IPROG may already
have taken effect. The platform must coordinate reset and SPI ownership so
other clients cannot collide with ongoing configuration. Trusted firmware
must recover from durable trial state and establish a safe configuration
state before rearming. There is no automatic retry.
