# h2 public-check controls: notes

The only specification source was `.benchmarks/E2E-SWE/tasks/h2/instruction.md`. Task tests, solution,
environment and `grade.json` were never read. The reference in `reference/` was written from the
instruction. It is deliberately minimal and validates the checker only.

## Deviations from `public-checks.plan.json`

- Defective controls: all 52 planned defects were kept with their planned suites and
  `expected_failed_ids`. No defect was dropped, replaced or re-targeted.
- `T.R03.02`: the planned "inspect the installed distribution's declared requirements" is not
  asserted (the atom lists it as a gap). There is also no check on which modules get imported. The
  image pre-installs `typing_extensions`, `packaging` and others, and the instruction does not
  forbid them, so the case checks only these two things:
  - a round trip works in the image that has only hyperframe/hpack as runtime packages;
  - the bytes emitted parse with hyperframe and hpack.
- `T.R06.04`: the plan suggested `MAX_CONCURRENT_STREAMS=10` as the hand-built upgrade setting.
  How that limit applies to a server's own streams is a stated gap (R06.11). So the hand-built
  header also carries `INITIAL_WINDOW_SIZE=100`, and the server's adoption of the client's
  settings is checked only through the window of stream 1:
  - `local_flow_control_window(1) == 100`;
  - a 101-byte send raises `FlowControlError`.
- `T.R01.01` / `T.R03.01` / `T.R06.01`: "socket creation blocked" is done with a `sys.addaudithook`
  hook in a fresh candidate interpreter. The hook rejects `socket.*`, `subprocess.Popen`,
  `os.system`, `os.exec`, `os.posix_spawn` and `os.spawn`. It is not done by monkeypatching
  `socket.socket`. File opens are not blocked, because imports need them.

## Ambiguities deliberately not asserted

- Which role and header encoding `H2Connection(config=None)` uses. Only construction and a
  bytes-only output are checked.
- Whether the request event list (`[RequestReceived, StreamEnded, ...]`) or the response list
  contains extra events. Order is checked as an ordered subsequence.
- `original_value` for advertised settings that have no documented default (`ENABLE_PUSH`,
  `MAX_HEADER_LIST_SIZE`).
- Whether the initial SETTINGS frame must advertise `MAX_CONCURRENT_STREAMS=100`. Only advertised
  values are compared with the defaults.
- Which `MAX_CONCURRENT_STREAMS` limits `send_headers`. Cases use only the peer-advertised value 1,
  which is below both, and never open more than 100 streams.
- How `local_flow_control_window` relates to the connection window: the stream window alone, or the
  minimum of stream and connection. Cases are built so that both readings agree. `T.R06.28` accepts
  either reading.
- When `acknowledge_received_data` emits WINDOW_UPDATE, and with what increment. Only the upper
  bound is checked: increments per target are at most the acknowledged bytes, and the server window
  grows by exactly what was sent.
- The `stream_id` of the connection-level `WindowUpdated` event.
- The `last_stream_id` sent by `close_connection(last_stream_id=None)`.
- The exception type raised after GOAWAY. Any class exported by `h2.exceptions` is accepted.
- How `ProtocolError`, `StreamClosedError`, `FlowControlError` and `FrameTooLargeError` inherit from
  one another. "Not the competing class" is asserted only when the two classes are unrelated.
- The default `exclusive` value of `prioritize`, weights outside 1-256, and `ping` with data that is
  not 8 bytes.
- The ALTSVC origin and `AlternativeServiceAvailable.origin`, and which side may send ALTSVC. Only
  `field_value` and the frame's stream are checked.
- What `stream_ended`, `priority_updated` and `remote_reset` contain (only their presence is
  checked), and whether `H2Configuration` attributes can be read.
- Whether the server-side upgrade call queues SETTINGS or returns a value, and whether repeated
  `get_next_available_stream_id()` calls without opening a stream return the same id.
- Whether the candidate must write `setup.sh` itself. The install receipt must succeed, but use of
  `setup.sh` is not required.

## Reference simplifications (`ponytail`)

The reference has no CONTINUATION reassembly, enforces no inbound stream limits or frame-size
limits, and has no priority tree. No case depends on any of these.
