"""Public acceptance cases for the held-out h2 task.

Authored from .benchmarks/E2E-SWE/tasks/h2/instruction.md only (line numbers below refer to it).
Top level imports the stdlib only; the candidate and hyperframe/hpack are imported inside cases.
Points the instruction leaves open (see atoms.json gaps) are never asserted.
"""
import base64
import json
import os
import re

CASES = {}


def case(test_id):
    def register(function):
        CASES[test_id] = function
        return function
    return register


MAGIC = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
REQ = [(":method", "GET"), (":path", "/"), (":scheme", "https"), (":authority", "example.com")]
PUSH = [(":method", "GET"), (":path", "/style.css"), (":scheme", "https"), (":authority", "example.com")]
STATUS = [(":status", "200")]
DEFAULTS = {"HEADER_TABLE_SIZE": 4096, "INITIAL_WINDOW_SIZE": 65535, "MAX_FRAME_SIZE": 16384,
            "MAX_CONCURRENT_STREAMS": 100}
SETTING_INTS = {"HEADER_TABLE_SIZE": 1, "ENABLE_PUSH": 2, "MAX_CONCURRENT_STREAMS": 3, "INITIAL_WINDOW_SIZE": 4,
                "MAX_FRAME_SIZE": 5, "MAX_HEADER_LIST_SIZE": 6}


def as_bytes(headers):
    return [(n.encode(), v.encode()) for n, v in headers]


# ----------------------------------------------------------------------------- candidate helpers

def h2():
    import h2.config  # noqa: F401 - the six public modules (instruction lines 10, 52-199)
    import h2.connection  # noqa: F401
    import h2.errors  # noqa: F401
    import h2.events  # noqa: F401
    import h2.exceptions  # noqa: F401
    import h2.settings  # noqa: F401
    import h2 as package
    return package


def conn(client_side, encoding=None):
    lib = h2()
    return lib.connection.H2Connection(config=lib.config.H2Configuration(client_side=client_side,
                                                                         header_encoding=encoding))


def send(src, dst):
    """Move src's queued bytes into dst; return dst's events as a list."""
    return list(dst.receive_data(src.data_to_send()))


def settle(client, server, limit=8):
    """Exchange queued bytes, client first, until both sides are quiet."""
    seen = {"client": [], "server": []}
    for _ in range(limit):
        to_server = client.data_to_send()
        if to_server:
            seen["server"] += list(server.receive_data(to_server))
        to_client = server.data_to_send()
        if to_client:
            seen["client"] += list(client.receive_data(to_client))
        if not to_server and not to_client:
            break
    return seen


def pair(client_enc=None, server_enc=None):
    """Client/server pair after the documented handshake (instruction lines 15-19)."""
    client, server = conn(True, client_enc), conn(False, server_enc)
    client.initiate_connection()
    server.initiate_connection()
    settle(client, server)
    return client, server


def request_pair(end_stream=True):
    client, server = pair()
    client.send_headers(1, REQ, end_stream=end_stream)
    send(client, server)
    return client, server


def frames(data, magic=False):
    """Parse a whole buffer as HTTP/2 frames with hyperframe (strict, nothing left over)."""
    from hyperframe.frame import Frame
    data = bytes(data)
    if magic:
        if not data.startswith(MAGIC):
            raise AssertionError("buffer does not start with the connection preface magic")
        data = data[len(MAGIC):]
    parsed, view = [], memoryview(data)
    while len(view):
        if len(view) < 9:
            raise AssertionError(f"{len(view)} trailing bytes do not form a frame header")
        frame, length = Frame.parse_frame_header(view[:9])
        if len(view) < 9 + length:
            raise AssertionError("truncated frame body")
        frame.parse_body(view[9:9 + length])
        parsed.append(frame)
        view = view[9 + length:]
    return parsed


def kind(frame_list, name):
    import hyperframe.frame as hf
    return [f for f in frame_list if isinstance(f, getattr(hf, name))]


def header_blocks(frame_list, decoder):
    """Decode HEADERS/PUSH_PROMISE (+CONTINUATION) blocks in order with one hpack decoder per direction."""
    import hyperframe.frame as hf
    blocks, current = [], None
    for frame in frame_list:
        if isinstance(frame, (hf.HeadersFrame, hf.PushPromiseFrame)):
            current = [frame, bytes(frame.data)]
        elif isinstance(frame, hf.ContinuationFrame) and current:
            current[1] += bytes(frame.data)
        else:
            continue
        if "END_HEADERS" in frame.flags:
            pairs = decoder.decode(current[1], raw=True)
            blocks.append((current[0], [(bytes(n).decode(), bytes(v).decode()) for n, v in pairs]))
            current = None
    return blocks


def events_of(events, name):
    cls = getattr(h2().events, name)
    return [e for e in events if isinstance(e, cls)]


def one(c, events, name, **attrs):
    """Exactly one event of the class matching attrs; returns it."""
    found = [e for e in events_of(events, name) if all(getattr(e, k, object()) == v for k, v in attrs.items())]
    c.equal(len(found), 1, f"number of {name} events with {attrs} in {events!r}")
    return found[0]


def in_order(c, events, expected, message):
    """expected: [(class name, {attr: value})] must appear as an ordered subsequence of events."""
    position = 0
    for name, attrs in expected:
        cls = getattr(h2().events, name)
        while position < len(events) and not (isinstance(events[position], cls) and all(
                getattr(events[position], k, object()) == v for k, v in attrs.items())):
            position += 1
        c.require(position < len(events), f"{message}: {name}{attrs} missing or out of order in {events!r}")
        position += 1


def exc(name):
    return getattr(h2().exceptions, name)


def raises_exactly(c, expected, competing, call, message):
    """Require exc(expected); also reject exc(competing) when the two classes are unrelated."""
    error = c.raises(exc(expected), call, message)
    wanted, other = exc(expected), exc(competing)
    if not issubclass(wanted, other) and not issubclass(other, wanted):
        c.require(not isinstance(error, other), f"{message}: raised {type(error).__name__}, a {competing}")
    return error


def raises_h2_error(c, call, message):
    """Some exception class exported by h2.exceptions (the instruction names no specific one)."""
    module = h2().exceptions
    classes = tuple(v for v in vars(module).values()
                    if isinstance(v, type) and issubclass(v, Exception) and v.__module__ != "builtins")
    c.require(classes, "h2.exceptions exports exception classes")
    return c.raises(classes, call, message)


def changed(event, name):
    return event.changed_settings[getattr(h2().settings.SettingCodes, name)]


def settings_frame(values, ack=False):
    from hyperframe.frame import SettingsFrame
    return SettingsFrame(0, settings={SETTING_INTS[k]: v for k, v in values.items()},
                         flags=["ACK"] if ack else []).serialize()


# ----------------------------------------------------------------------------- isolated subprocess script

GUARD = r'''
import json, sys
blocked = []
def _guard(event, args):
    if event.startswith("socket.") or event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn"):
        blocked.append(event)
        raise RuntimeError("blocked I/O audit event " + event)
sys.addaudithook(_guard)
'''

ROUND_TRIP = GUARD + r'''
import h2.connection, h2.config, h2.events, h2.errors, h2.settings, h2.exceptions
client = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=True))
server = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=False))
c2s, s2c, names = [], [], []
def pump():
    for _ in range(8):
        a = client.data_to_send()
        if a:
            c2s.append(a.hex()); names.extend(type(e).__name__ for e in server.receive_data(a))
        b = server.data_to_send()
        if b:
            s2c.append(b.hex()); names.extend(type(e).__name__ for e in client.receive_data(b))
        if not a and not b:
            return
REQ = [(":method", "GET"), (":path", "/"), (":scheme", "https"), (":authority", "example.com")]
client.initiate_connection(); server.initiate_connection(); pump()
client.send_headers(1, REQ + [("x-stream", "one")])
client.send_headers(3, REQ + [("x-stream", "three")], end_stream=True)
client.send_data(1, b"upload", end_stream=True)
pump()
server.send_headers(1, [(":status", "200")]); server.send_data(1, b"a" * 1000, end_stream=True)
server.send_headers(3, [(":status", "204")], end_stream=True)
pump()
client.increment_flow_control_window(1000)
client.update_settings({h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: 50})
pump()
files = {m: getattr(sys.modules[m], "__file__", None) for m in
         ("h2.connection", "h2.config", "h2.events", "h2.errors", "h2.settings", "h2.exceptions")}
print(json.dumps({"c2s": c2s, "s2c": s2c, "events": names, "files": files, "blocked": blocked}))
'''


def round_trip(c):
    """Run ROUND_TRIP in a fresh candidate interpreter (empty cwd, socket/subprocess audit-blocked)."""
    done = c.run_python(ROUND_TRIP)
    c.require(done.returncode == 0, f"round trip with blocked I/O exits 0 (rc={done.returncode}): {done.stderr[-1500:]}")
    result = json.loads(done.stdout.strip().splitlines()[-1])
    c.equal(result["blocked"], [], "audit events for sockets/subprocesses during import and use")
    return result


def check_round_trip_wire(c, result):
    from hpack import Decoder
    c2s = frames(b"".join(bytes.fromhex(x) for x in result["c2s"]), magic=True)
    s2c = frames(b"".join(bytes.fromhex(x) for x in result["s2c"]))
    types = {type(f).__name__ for f in c2s}
    c.require({"SettingsFrame", "HeadersFrame", "DataFrame", "WindowUpdateFrame"} <= types,
              f"client frames include SETTINGS/HEADERS/DATA/WINDOW_UPDATE: {sorted(types)}")
    c.require({"SettingsFrame", "HeadersFrame", "DataFrame"} <= {type(f).__name__ for f in s2c},
              "server frames include SETTINGS/HEADERS/DATA")
    requests = header_blocks(c2s, Decoder())
    c.equal(sorted(f.stream_id for f, _ in requests), [1, 3], "client HEADERS stream ids (multiplexed)")
    for frame, block in requests:
        c.require(all(h in block for h in REQ), f"stream {frame.stream_id} request headers decode with hpack: {block}")
    responses = {f.stream_id: block for f, block in header_blocks(s2c, Decoder())}
    c.require((":status", "200") in responses.get(1, []) and (":status", "204") in responses.get(3, []),
              f"server header blocks decode with hpack: {responses}")
    data = b"".join(bytes(f.data) for f in kind(s2c, "DataFrame") if f.stream_id == 1)
    c.equal(data, b"a" * 1000, "server DATA payload on stream 1")


# ============================================================================ install-surface

@case("T.R01.01")
def _(c):
    # Lines 3, 10: pure-Python sans-I/O library; six modules; the pair only exchanges byte buffers.
    c.equal(c.ctx["install"].get("returncode"), 0, "offline install exit status")
    result = round_trip(c)
    for module, path in result["files"].items():
        c.require(isinstance(path, str) and path.endswith(".py"), f"{module} is a pure-Python module: {path}")
    check_round_trip_wire(c, result)
    for name in ("RequestReceived", "ResponseReceived", "DataReceived", "StreamEnded", "RemoteSettingsChanged",
                 "WindowUpdated"):
        c.require(name in result["events"], f"{name} produced by the byte exchange: {result['events']}")


@case("T.R03.01")
def _(c):
    # Lines 34-35: offline; nothing installed, downloaded or fetched; no network access attempt.
    receipt = c.ctx["install"]
    c.equal(receipt.get("pip_no_index"), "1", "install ran with PIP_NO_INDEX=1")
    c.equal(receipt.get("returncode"), 0, f"offline install exit status ({receipt.get('stderr_tail', '')[-800:]})")
    round_trip(c)


@case("T.R03.02")
def _(c):
    # Lines 37-38: works with the pre-installed hyperframe/hpack; frames parse with hyperframe, blocks decode with hpack.
    check_round_trip_wire(c, round_trip(c))


@case("T.R04.01")
def _(c):
    # Lines 42-45: setup.sh runs `pip install -e . --no-build-isolation` offline; h2 imports from the editable install.
    receipt = c.ctx["install"]
    c.equal(receipt.get("returncode"), 0, f"setup exit status ({receipt.get('stderr_tail', '')[-800:]})")
    done = c.run_python("import os, h2.connection; print(os.path.realpath(h2.connection.__file__))")
    c.equal(done.returncode, 0, f"import h2.connection from an unrelated directory: {done.stderr[-800:]}")
    project = os.path.realpath(c.ctx["project"])
    location = done.stdout.strip()
    c.require(location.startswith(project + os.sep), f"h2 imported from the editable project {project}, got {location}")


@case("T.R08.01")
def _(c):
    # Lines 155-169: ErrorCodes integer constants; ErrorCodes.CANCEL accepted by reset_stream.
    codes = h2().errors.ErrorCodes
    table = {"NO_ERROR": 0, "PROTOCOL_ERROR": 1, "INTERNAL_ERROR": 2, "FLOW_CONTROL_ERROR": 3, "SETTINGS_TIMEOUT": 4,
             "STREAM_CLOSED": 5, "FRAME_SIZE_ERROR": 6, "REFUSED_STREAM": 7, "CANCEL": 8, "COMPRESSION_ERROR": 9,
             "ENHANCE_YOUR_CALM": 11}
    for name, value in table.items():
        c.require(hasattr(codes, name), f"ErrorCodes.{name} exists")
        c.require(getattr(codes, name) == value, f"ErrorCodes.{name} == {value}, got {getattr(codes, name)!r}")
    client, _server = pair()
    client.send_headers(1, REQ)
    client.data_to_send()
    client.reset_stream(1, error_code=codes.CANCEL)
    rst = kind(frames(client.data_to_send()), "RstStreamFrame")
    c.equal([(f.stream_id, f.error_code) for f in rst], [(1, 8)], "RST_STREAM carries ErrorCodes.CANCEL")


@case("T.R09.01")
def _(c):
    # Lines 175-184: SettingCodes integer constants, usable as dict keys.
    codes = h2().settings.SettingCodes
    for name, value in SETTING_INTS.items():
        c.require(hasattr(codes, name), f"SettingCodes.{name} exists")
        c.require(getattr(codes, name) == value, f"SettingCodes.{name} == {value}, got {getattr(codes, name)!r}")
        c.equal({getattr(codes, name): "x"}.get(getattr(codes, name)), "x", f"SettingCodes.{name} works as a dict key")
    client, server = pair()
    client.update_settings({codes.MAX_CONCURRENT_STREAMS: 50})
    event = one(c, send(client, server), "RemoteSettingsChanged")
    c.equal(event.changed_settings[codes.MAX_CONCURRENT_STREAMS].new_value, 50, "changed_settings keyed by SettingCodes")


@case("T.R10.01")
def _(c):
    # Lines 194-199: six exception classes, raised under their documented conditions.
    for name in ("ProtocolError", "TooManyStreamsError", "FlowControlError", "FrameTooLargeError",
                 "NoSuchStreamError", "StreamClosedError"):
        cls = getattr(h2().exceptions, name, None)
        c.require(isinstance(cls, type) and issubclass(cls, Exception), f"h2.exceptions.{name} is an Exception subclass")
    client, server = pair()
    c.raises(exc("ProtocolError"), lambda: client.send_headers(2, REQ), "even client stream id -> ProtocolError")
    c.raises(exc("NoSuchStreamError"), lambda: client.local_flow_control_window(7), "unknown stream -> NoSuchStreamError")
    client.send_headers(1, REQ)
    raises_exactly(c, "FrameTooLargeError", "FlowControlError", lambda: client.send_data(1, b"x" * 16385),
                   "16385-byte DATA -> FrameTooLargeError")
    for _ in range(3):
        client.send_data(1, b"x" * 16384)
    raises_exactly(c, "FlowControlError", "FrameTooLargeError", lambda: client.send_data(1, b"x" * 16384),
                   "DATA beyond the window -> FlowControlError")
    client, server = pair()
    server.update_settings({h2().settings.SettingCodes.MAX_CONCURRENT_STREAMS: 1})
    settle(client, server)
    client.send_headers(1, REQ)
    c.raises(exc("TooManyStreamsError"), lambda: client.send_headers(3, REQ), "second stream beyond MAX_CONCURRENT_STREAMS=1")


# ============================================================================ handshake-config

@case("T.R02.01")
def _(c):
    # Line 7: send methods queue; data_to_send() drains; receive_data() returns the events.
    client, server = pair()
    client.ping(b"12345678")
    out = client.data_to_send()
    c.require(isinstance(out, bytes) and out, "data_to_send returns the queued bytes")
    c.equal(client.data_to_send(), b"", "second data_to_send after draining")
    got = server.receive_data(out)
    c.require(isinstance(got, list), f"receive_data returns a list, got {type(got).__name__}")
    c.equal([e.ping_data for e in events_of(got, "PingReceived")], [b"12345678"], "PingReceived from the queued bytes")
    client.send_headers(1, REQ, end_stream=True)
    out = client.data_to_send()
    c.equal(client.data_to_send(), b"", "data_to_send drained after send_headers")
    got = server.receive_data(out)
    c.require(isinstance(got, list), "receive_data returns a list for HEADERS")
    one(c, got, "RequestReceived", stream_id=1)


@case("T.R02.02")
def _(c):
    # Lines 10-19: the example construction and handshake, exactly as shown.
    import h2.connection, h2.config, h2.events  # noqa: E401,F401 - the example's import line
    client = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=True))
    server = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=False))
    client.initiate_connection()
    server.initiate_connection()
    first = server.receive_data(client.data_to_send())
    second = client.receive_data(server.data_to_send())
    c.require(isinstance(first, list) and isinstance(second, list),
              f"both receive_data calls return lists: {type(first).__name__}, {type(second).__name__}")
    client.send_headers(1, REQ, end_stream=True)
    c.require(kind(frames(client.data_to_send()), "HeadersFrame"), "the request step succeeds after the handshake")


@case("T.R05.01")
def _(c):
    # Line 52: H2Configuration(client_side=True, header_encoding=None) keywords and defaults.
    lib = h2()
    default_client = lib.connection.H2Connection(config=lib.config.H2Configuration())
    utf8_server = lib.connection.H2Connection(config=lib.config.H2Configuration(client_side=False,
                                                                                header_encoding="utf-8"))
    default_client.initiate_connection()
    preface = default_client.data_to_send()
    c.require(preface.startswith(MAGIC), "no-argument configuration sends the client preface")
    c.equal(default_client.get_next_available_stream_id(), 1, "no-argument configuration uses odd (client) ids")
    utf8_server.initiate_connection()
    utf8_server.receive_data(preface)
    settle(default_client, utf8_server)
    default_client.send_headers(1, REQ, end_stream=True)
    request = one(c, send(default_client, utf8_server), "RequestReceived", stream_id=1)
    c.equal([tuple(h) for h in request.headers], REQ, "header_encoding='utf-8' server sees str headers")
    utf8_server.send_headers(1, STATUS, end_stream=True)
    response = one(c, send(utf8_server, default_client), "ResponseReceived", stream_id=1)
    c.require(all(isinstance(n, bytes) and isinstance(v, bytes) for n, v in response.headers),
              f"default header_encoding=None yields bytes headers: {response.headers!r}")


@case("T.R05.02")
def _(c):
    # Line 54: client_side selects preface and stream id parity.
    client, server = conn(True), conn(False)
    client.initiate_connection()
    server.initiate_connection()
    c.require(client.data_to_send().startswith(MAGIC), "client emits the preface magic")
    c.require(MAGIC not in server.data_to_send(), "server emits no preface magic")
    c.equal(client.get_next_available_stream_id() % 2, 1, "client stream ids are odd")
    c.equal(server.get_next_available_stream_id() % 2, 0, "server stream ids are even")


@case("T.R05.03")
def _(c):
    # Lines 55-57: header_encoding None -> bytes tuples, "utf-8" -> str tuples.
    for encoding, expected in ((None, as_bytes(REQ)), ("utf-8", REQ)):
        client, server = pair(server_enc=encoding)
        client.send_headers(1, REQ, end_stream=True)
        request = one(c, send(client, server), "RequestReceived", stream_id=1)
        c.equal([tuple(h) for h in request.headers], expected, f"RequestReceived headers with header_encoding={encoding!r}")
        c.require(all(type(n) is type(expected[0][0]) and type(v) is type(expected[0][1]) for n, v in request.headers),
                  f"header element types with header_encoding={encoding!r}")


@case("T.R06.01")
def _(c):
    # Line 63: H2Connection(config=None) and with a config construct; no network I/O.
    done = c.run_python(GUARD + r'''
import h2.connection, h2.config
a = h2.connection.H2Connection()
b = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=False))
a.initiate_connection(); b.initiate_connection()
print(json.dumps({"a": type(a.data_to_send()).__name__, "b": type(b.data_to_send()).__name__, "blocked": blocked}))
''')
    c.equal(done.returncode, 0, f"both constructions succeed with sockets blocked: {done.stderr[-1500:]}")
    result = json.loads(done.stdout.strip().splitlines()[-1])
    c.equal((result["a"], result["b"]), ("bytes", "bytes"), "both connections only produce byte buffers")
    c.equal(result["blocked"], [], "no socket/subprocess audit events")


@case("T.R06.02")
def _(c):
    # Line 67: client preface = 24-byte magic + SETTINGS; server preface = SETTINGS.
    client, server = conn(True), conn(False)
    client.initiate_connection()
    server.initiate_connection()
    out = client.data_to_send()
    c.equal(out[:24], MAGIC, "client output starts with the 24-byte magic")
    parsed = frames(out, magic=True)
    c.require(parsed and type(parsed[0]).__name__ == "SettingsFrame", f"magic followed by SETTINGS: {parsed}")
    c.require(parsed[0].stream_id == 0 and "ACK" not in parsed[0].flags, "client SETTINGS is non-ACK on stream 0")
    out = server.data_to_send()
    c.require(MAGIC not in out, "server output contains no magic")
    parsed = frames(out)
    c.require(parsed and type(parsed[0]).__name__ == "SettingsFrame" and "ACK" not in parsed[0].flags,
              f"server output starts with a non-ACK SETTINGS frame: {parsed}")


@case("T.R06.05")
def _(c):
    # Line 73: receive_data returns events and queues SETTINGS ACK and PING ACK.
    from hyperframe.frame import PingFrame
    server = conn(False)
    server.initiate_connection()
    server.data_to_send()
    got = server.receive_data(MAGIC + settings_frame({"MAX_CONCURRENT_STREAMS": 100})
                              + PingFrame(0, opaque_data=b"abcdefgh").serialize())
    c.require(isinstance(got, list), f"receive_data returns a list, got {type(got).__name__}")
    out = frames(server.data_to_send())
    c.require(any("ACK" in f.flags for f in kind(out, "SettingsFrame")), f"SETTINGS ACK queued: {out}")
    c.require(any("ACK" in f.flags and f.opaque_data == b"abcdefgh" for f in kind(out, "PingFrame")),
              f"PING ACK with the same 8 bytes queued: {out}")


@case("T.R06.06")
def _(c):
    # Line 73: handshake RemoteSettingsChanged enumerates every advertised setting, even default-valued ones.
    scenarios = [(False, dict(DEFAULTS)),
                 (False, {"MAX_CONCURRENT_STREAMS": 50, "INITIAL_WINDOW_SIZE": 1000}),
                 (True, dict(DEFAULTS))]
    for client_side, advertised in scenarios:
        receiver = conn(client_side)
        receiver.initiate_connection()
        receiver.data_to_send()
        got = list(receiver.receive_data((b"" if client_side else MAGIC) + settings_frame(advertised)))
        event = one(c, got, "RemoteSettingsChanged")
        for name, value in advertised.items():
            entry = event.changed_settings.get(getattr(h2().settings.SettingCodes, name))
            c.require(entry is not None, f"{'client' if client_side else 'server'}: {name} listed in changed_settings")
            c.equal((entry.original_value, entry.new_value), (DEFAULTS[name], value),
                    f"{name} (original_value, new_value)")


@case("T.R06.07")
def _(c):
    # Line 75: data_to_send returns pending bytes or b"".
    client = conn(True)
    c.equal(client.data_to_send(), b"", "fresh connection has nothing queued")
    client.initiate_connection()
    first = client.data_to_send()
    c.require(isinstance(first, bytes) and first.startswith(MAGIC), "queued preface returned as bytes")
    c.equal(client.data_to_send(), b"", "immediately following call")


@case("T.R06.08")
def _(c):
    # Line 77: clear_outbound_data_buffer discards pending output.
    client = conn(True)
    client.initiate_connection()
    client.clear_outbound_data_buffer()
    c.equal(client.data_to_send(), b"", "data_to_send after clearing")
    client.ping(b"pingpong")
    out = client.data_to_send()
    c.require(MAGIC not in out, "discarded preface never reappears")
    parsed = frames(out)
    c.equal([(type(f).__name__, f.opaque_data) for f in parsed], [("PingFrame", b"pingpong")],
            "only the later PING is sent")


@case("T.R07.02")
def _(c):
    # Line 149: headers are lists of (name, value) tuples: bytes by default, str with "utf-8".
    for encoding, element in ((None, bytes), ("utf-8", str)):
        client, server = pair(encoding, encoding)
        client.send_headers(1, REQ)
        client.send_headers(1, [("x-trailer", "done")], end_stream=True)
        got = send(client, server)
        server.push_stream(1, server.get_next_available_stream_id(), PUSH)
        server.send_headers(1, STATUS, end_stream=True)
        got += send(server, client)
        for name in ("RequestReceived", "TrailersReceived", "PushedStreamReceived", "ResponseReceived"):
            event = one(c, got, name)
            c.require(isinstance(event.headers, list) and event.headers, f"{name}.headers is a non-empty list")
            c.require(all(isinstance(h, tuple) and len(h) == 2 and all(isinstance(x, element) for x in h)
                          for h in event.headers),
                      f"{name}.headers are ({element.__name__}, {element.__name__}) tuples with "
                      f"header_encoding={encoding!r}: {event.headers!r}")


@case("T.R09.02")
def _(c):
    # Line 188: local defaults 4096/65535/16384 and MAX_CONCURRENT_STREAMS 100 (not unlimited).
    for client_side in (True, False):
        node = conn(client_side)
        node.initiate_connection()
        initial = kind(frames(node.data_to_send(), magic=client_side), "SettingsFrame")
        c.require(initial, "initial SETTINGS frame emitted")
        for name, value in DEFAULTS.items():
            if SETTING_INTS[name] in initial[0].settings:
                c.equal(initial[0].settings[SETTING_INTS[name]], value, f"advertised {name}")
        got = list(node.receive_data((b"" if client_side else MAGIC) + settings_frame(DEFAULTS)))
        event = one(c, got, "RemoteSettingsChanged")
        for name, value in DEFAULTS.items():
            c.equal(changed(event, name).original_value, value, f"{name} original_value (documented default)")


@case("T.R09.03")
def _(c):
    # Line 188: the local default does not constrain the peer's settings.
    for client_side in (False, True):
        node = conn(client_side)
        node.initiate_connection()
        node.data_to_send()
        got = list(node.receive_data((b"" if client_side else MAGIC) + settings_frame({"MAX_CONCURRENT_STREAMS": 200})))
        c.equal(changed(one(c, got, "RemoteSettingsChanged"), "MAX_CONCURRENT_STREAMS").new_value, 200,
                "peer MAX_CONCURRENT_STREAMS=200 reported as advertised")
        c.require(any("ACK" in f.flags for f in kind(frames(node.data_to_send()), "SettingsFrame")),
                  "the 200 advertisement is accepted (acknowledged)")


# ============================================================================ request-response

@case("T.R02.03")
def _(c):
    # Lines 20-24: the example GET arrives as RequestReceived then StreamEnded.
    client, server = pair()
    client.send_headers(1, REQ, end_stream=True)
    got = send(client, server)
    request = one(c, got, "RequestReceived", stream_id=1)
    headers = [tuple(h) for h in request.headers]
    c.require(all(h in headers for h in as_bytes(REQ)), f"request headers as bytes tuples: {headers}")
    in_order(c, got, [("RequestReceived", {"stream_id": 1}), ("StreamEnded", {"stream_id": 1})], "request events")


@case("T.R02.04")
def _(c):
    # Lines 25-29: the example response arrives as ResponseReceived, DataReceived, StreamEnded in order.
    client, server = request_pair()
    server.send_headers(1, STATUS)
    server.send_data(1, b"hello", end_stream=True)
    got = send(server, client)
    response = one(c, got, "ResponseReceived", stream_id=1)
    c.require((b":status", b"200") in [tuple(h) for h in response.headers], f"(b':status', b'200') in {response.headers}")
    in_order(c, got, [("ResponseReceived", {"stream_id": 1}), ("DataReceived", {"stream_id": 1, "data": b"hello"}),
                      ("StreamEnded", {"stream_id": 1})], "response events")


@case("T.R06.09")
def _(c):
    # Line 81: send_headers emits one HEADERS frame, opens the stream, honours end_stream.
    from hpack import Decoder
    for end_stream in (False, True):
        client, _server = pair()
        client.send_headers(1, REQ, end_stream=end_stream)
        parsed = frames(client.data_to_send())
        headers = kind(parsed, "HeadersFrame")
        c.equal([f.stream_id for f in headers], [1], f"one HEADERS frame on stream 1 (end_stream={end_stream})")
        c.equal(header_blocks(parsed, Decoder())[0][1], REQ, "header block decodes to the given headers")
        c.equal("END_STREAM" in headers[0].flags, end_stream, f"END_STREAM flag with end_stream={end_stream}")
        c.equal(client.open_outbound_streams, 1, "the stream counts as open")
        if end_stream:
            c.raises(exc("ProtocolError"), lambda: client.send_data(1, b"x"), "send_data after end_stream=True")


@case("T.R06.10")
def _(c):
    # Line 81: odd, increasing client ids; closed streams rejected.
    client, _server = pair()
    c.raises(exc("ProtocolError"), lambda: client.send_headers(2, REQ), "even client stream id")
    client.send_headers(5, REQ)
    c.raises(exc("ProtocolError"), lambda: client.send_headers(3, REQ), "decreasing client stream id")
    client, _server = pair()
    client.send_headers(1, REQ)
    client.reset_stream(1)
    c.raises(exc("ProtocolError"), lambda: client.send_headers(1, REQ), "send_headers on a reset stream")
    client, server = request_pair()
    server.send_headers(1, STATUS, end_stream=True)
    send(server, client)
    c.raises(exc("ProtocolError"), lambda: client.send_headers(1, REQ), "send_headers on a stream closed on both sides")


@case("T.R06.12")
def _(c):
    # Line 83: each send_data call emits exactly one DATA frame.
    client, server = pair()
    client.send_headers(1, REQ)
    send(client, server)
    got = []
    for payload, end_stream in ((b"hello", False), (b"x" * 16384, True)):
        client.send_data(1, payload, end_stream=end_stream)
        out = client.data_to_send()
        data = kind(frames(out), "DataFrame")
        c.equal([(f.stream_id, bytes(f.data)) for f in data], [(1, payload)], f"one DATA frame for {len(payload)} bytes")
        c.equal("END_STREAM" in data[0].flags, end_stream, f"END_STREAM with end_stream={end_stream}")
        got += list(server.receive_data(out))
    received = b"".join(e.data for e in events_of(got, "DataReceived") if e.stream_id == 1)
    c.equal(received, b"hello" + b"x" * 16384, "peer DataReceived payload")
    in_order(c, got, [("DataReceived", {"stream_id": 1}), ("StreamEnded", {"stream_id": 1})], "data then end")


@case("T.R06.17")
def _(c):
    # Line 85: end_stream sends an empty DATA frame with END_STREAM.
    client, server = pair()
    client.send_headers(1, REQ)
    send(client, server)
    client.end_stream(1)
    out = client.data_to_send()
    data = kind(frames(out), "DataFrame")
    c.equal([(f.stream_id, bytes(f.data), "END_STREAM" in f.flags) for f in data], [(1, b"", True)],
            "one empty END_STREAM DATA frame")
    one(c, list(server.receive_data(out)), "StreamEnded", stream_id=1)
    c.raises(exc("ProtocolError"), lambda: client.send_data(1, b"x"), "send_data after end_stream")


@case("T.R06.18")
def _(c):
    # Line 89: next stream id parity and increment by 2 as streams are opened.
    client, server = pair()
    for expected in (1, 3, 5):
        stream_id = client.get_next_available_stream_id()
        c.equal(stream_id, expected, "client next stream id")
        client.send_headers(stream_id, REQ, end_stream=True)
    client, server = request_pair()
    for expected in (2, 4):
        stream_id = server.get_next_available_stream_id()
        c.equal(stream_id, expected, "server next stream id")
        server.push_stream(1, stream_id, PUSH)


@case("T.R06.33")
def _(c):
    # Lines 121-122: open stream counters include half-closed streams.
    client, server = pair()
    client.send_headers(1, REQ)
    client.send_headers(3, REQ)
    send(client, server)
    counts = lambda: (client.open_outbound_streams, server.open_inbound_streams,  # noqa: E731
                      client.open_inbound_streams, server.open_outbound_streams)
    c.equal(counts(), (2, 2, 0, 0), "after opening 1 and 3")
    client.end_stream(1)
    send(client, server)
    c.equal(counts(), (2, 2, 0, 0), "stream 1 half-closed still counts")
    server.send_headers(1, STATUS, end_stream=True)
    send(server, client)
    c.equal(counts(), (1, 1, 0, 0), "stream 1 closed on both sides")
    client.reset_stream(3)
    send(client, server)
    c.equal(counts(), (0, 0, 0, 0), "stream 3 reset")


@case("T.R07.01")
def _(c):
    # Lines 129-147: every event class with its documented attributes.
    lib = h2()
    client, server = conn(True), conn(False)
    client.initiate_connection()
    server.initiate_connection()
    got = send(client, server)
    settings = one(c, got, "RemoteSettingsChanged")
    c.require(isinstance(settings.changed_settings, dict) and settings.changed_settings, "changed_settings dict")
    for entry in settings.changed_settings.values():
        c.require(hasattr(entry, "original_value") and hasattr(entry, "new_value"), "ChangedSetting attributes")
    got = send(server, client)
    send(client, server)
    got = send(server, client) + got
    c.require(hasattr(one(c, got, "SettingsAcknowledged"), "changed_settings"), "SettingsAcknowledged.changed_settings")

    client.send_headers(1, REQ)
    client.send_data(1, b"body")
    client.send_headers(1, [("x-trailer", "done")], end_stream=True)
    got = send(client, server)
    in_order(c, got, [("RequestReceived", {"stream_id": 1}), ("DataReceived", {"stream_id": 1}),
                      ("TrailersReceived", {"stream_id": 1}), ("StreamEnded", {"stream_id": 1})], "wire order")
    for name in ("RequestReceived", "TrailersReceived"):
        event = one(c, got, name)
        c.require(all(hasattr(event, a) for a in ("stream_id", "headers", "stream_ended", "priority_updated")),
                  f"{name} attributes")
    data = one(c, got, "DataReceived")
    c.require(isinstance(data.data, bytes) and data.data == b"body", "DataReceived.data is bytes")
    c.require(hasattr(data, "flow_controlled_length") and data.flow_controlled_length >= len(data.data),
              "DataReceived.flow_controlled_length >= len(data)")
    c.require(hasattr(data, "stream_ended"), "DataReceived.stream_ended")

    server.push_stream(1, 2, PUSH)
    got = send(server, client)
    pushed = one(c, got, "PushedStreamReceived")
    c.equal((pushed.parent_stream_id, pushed.pushed_stream_id), (1, 2), "PushedStreamReceived ids")
    c.require(isinstance(pushed.headers, list), "PushedStreamReceived.headers")

    server.send_headers(1, STATUS)
    server.send_data(1, b"ok")
    got = send(server, client)
    response = one(c, got, "ResponseReceived", stream_id=1)
    c.require(all(hasattr(response, a) for a in ("headers", "stream_ended", "priority_updated")),
              "ResponseReceived attributes")
    one(c, got, "DataReceived", stream_id=1, data=b"ok")

    client.increment_flow_control_window(100, stream_id=1)
    one(c, send(client, server), "WindowUpdated", stream_id=1, delta=100)
    client.prioritize(1, weight=32, depends_on=0, exclusive=False)
    one(c, send(client, server), "PriorityUpdated", stream_id=1, weight=32, depends_on=0, exclusive=False)
    server.advertise_alternative_service(b'h2=":8000"', stream_id=1)
    alt = one(c, send(server, client), "AlternativeServiceAvailable", field_value=b'h2=":8000"')
    c.require(hasattr(alt, "origin"), "AlternativeServiceAvailable.origin")
    client.ping(b"pingdata")
    one(c, send(client, server), "PingReceived", ping_data=b"pingdata")
    one(c, send(server, client), "PingAckReceived", ping_data=b"pingdata")

    client.send_headers(3, REQ)
    send(client, server)
    client.reset_stream(3, error_code=lib.errors.ErrorCodes.CANCEL)
    reset = one(c, send(client, server), "StreamReset", stream_id=3)
    c.equal(reset.error_code, 8, "StreamReset.error_code")
    c.require(hasattr(reset, "remote_reset"), "StreamReset.remote_reset")
    server.close_connection(error_code=0, last_stream_id=3)
    term = one(c, send(server, client), "ConnectionTerminated")
    c.equal((term.error_code, term.last_stream_id), (0, 3), "ConnectionTerminated error_code/last_stream_id")
    c.require(hasattr(term, "additional_data"), "ConnectionTerminated.additional_data")


@case("T.integration.get-round-trip")
def _(c):
    # Lines 9-30 executed verbatim (and with header_encoding="utf-8"); every buffer parses as frames.
    from hpack import Decoder
    lib = h2()
    usage_head = (
        'import h2.connection, h2.config, h2.events\n\n'
        'client = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=True{enc}))\n'
        'server = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=False{enc}))\n\n'
        'client.initiate_connection()\n'
        'server.initiate_connection()\n'
        'server.receive_data(client.data_to_send())\n'
        'client.receive_data(server.data_to_send())\n\n'
        'client.send_headers(1, [(":method", "GET"), (":path", "/"),\n'
        '                        (":scheme", "https"), (":authority", "example.com")], end_stream=True)\n'
        'events = server.receive_data(client.data_to_send())  # -> [RequestReceived, StreamEnded, ...]\n')
    usage_tail = (
        'server.send_headers(1, [(":status", "200")])\n'
        'server.send_data(1, b"hello", end_stream=True)\n'
        'events = client.receive_data(server.data_to_send())  # -> [ResponseReceived, DataReceived, StreamEnded]\n')
    H2Connection = lib.connection.H2Connection
    original = H2Connection.__dict__.get("data_to_send")
    inherited = H2Connection.data_to_send
    for enc, convert in (("", as_bytes), (', header_encoding="utf-8"', lambda h: h)):
        log = []

        def recording(self, *args, **kwargs):
            out = inherited(self, *args, **kwargs)
            log.append(out)
            return out
        H2Connection.data_to_send = recording
        try:
            namespace = {}
            exec(usage_head.format(enc=enc), namespace)
            server_events = list(namespace["events"])
            exec(usage_tail, namespace)
            client_events = list(namespace["events"])
        finally:
            if original is None:
                del H2Connection.data_to_send
            else:
                H2Connection.data_to_send = original
        label = "utf-8" if enc else "default"
        request = one(c, server_events, "RequestReceived", stream_id=1)
        c.require(all(h in [tuple(x) for x in request.headers] for h in convert(REQ)),
                  f"{label}: request headers {request.headers!r}")
        in_order(c, server_events, [("RequestReceived", {"stream_id": 1}), ("StreamEnded", {"stream_id": 1})],
                 f"{label}: server events")
        response = one(c, client_events, "ResponseReceived", stream_id=1)
        c.require(convert(STATUS)[0] in [tuple(x) for x in response.headers], f"{label}: response headers")
        in_order(c, client_events, [("ResponseReceived", {"stream_id": 1}),
                                    ("DataReceived", {"stream_id": 1, "data": b"hello"}),
                                    ("StreamEnded", {"stream_id": 1})], f"{label}: client events")
        # The example calls data_to_send() four times: client, server, client, server (lines 18, 19, 24, 29).
        c.equal(len(log), 4, f"{label}: data_to_send calls in the example")
        to_server = frames(log[0] + log[2], magic=True)
        to_client = frames(log[1] + log[3])
        c.require(any(f.stream_id == 1 and "END_STREAM" in f.flags for f in kind(to_server, "HeadersFrame")),
                  f"{label}: request HEADERS with END_STREAM")
        c.require(any(h in REQ for _, block in header_blocks(to_server, Decoder()) for h in block),
                  f"{label}: request header block decodes with hpack")
        c.require((":status", "200") in [h for _, block in header_blocks(to_client, Decoder()) for h in block],
                  f"{label}: response header block decodes with hpack")


# ============================================================================ flow-control

@case("T.R06.13")
def _(c):
    # Line 83: FlowControlError when len(data) exceeds the window.
    client, _server = pair()
    client.send_headers(1, REQ)
    for _ in range(3):
        client.send_data(1, b"x" * 16384)
    raises_exactly(c, "FlowControlError", "FrameTooLargeError", lambda: client.send_data(1, b"x" * 16384),
                   "16384 bytes with 16383 left in the window")


@case("T.R06.14")
def _(c):
    # Line 83: FrameTooLargeError above MAX_FRAME_SIZE; a call never splits into several frames.
    client, _server = pair()
    client.send_headers(1, REQ)
    client.data_to_send()
    raises_exactly(c, "FrameTooLargeError", "FlowControlError", lambda: client.send_data(1, b"x" * 16385),
                   "16385 bytes with MAX_FRAME_SIZE 16384")
    c.equal(kind(frames(client.data_to_send()), "DataFrame"), [], "no DATA frame emitted for the rejected call")


@case("T.R06.15")
def _(c):
    # Line 83: the flow-control window is checked first.
    client, _server = pair()
    client.send_headers(1, REQ)
    raises_exactly(c, "FlowControlError", "FrameTooLargeError", lambda: client.send_data(1, b"x" * 65536),
                   "65536 bytes exceeds both limits")
    client, _server = pair()
    client.send_headers(1, REQ)
    for size in (16384, 16384, 16384, 16383):
        client.send_data(1, b"x" * size)
    raises_exactly(c, "FlowControlError", "FrameTooLargeError", lambda: client.send_data(1, b"x" * 16385),
                   "16385 bytes on an exhausted window")


@case("T.R06.16")
def _(c):
    # Line 83: ProtocolError when the send side is already closed.
    client, _server = pair()
    client.send_headers(1, REQ, end_stream=True)
    c.raises(exc("ProtocolError"), lambda: client.send_data(1, b"x"), "after send_headers(end_stream=True)")
    client, _server = pair()
    client.send_headers(1, REQ)
    client.end_stream(1)
    c.raises(exc("ProtocolError"), lambda: client.send_data(1, b"x"), "after end_stream(1)")


@case("T.R06.25")
def _(c):
    # Line 101: local_flow_control_window tracks the bytes the local side can send.
    client, _server = pair()
    client.send_headers(1, REQ)
    c.equal(client.local_flow_control_window(1), 65535, "initial local window")
    client.send_data(1, b"x" * 1000)
    c.equal(client.local_flow_control_window(1), 64535, "after sending 1000 bytes")


@case("T.R06.26")
def _(c):
    # Line 101: NoSuchStreamError for an unknown stream.
    client, _server = pair()
    c.raises(exc("NoSuchStreamError"), lambda: client.local_flow_control_window(7), "stream 7 was never opened")


@case("T.R06.27")
def _(c):
    # Line 103: remote_flow_control_window reports the peer's window on the stream.
    client, server = request_pair()
    c.equal(client.remote_flow_control_window(1), 65535, "initial remote window")
    server.send_headers(1, STATUS)
    server.send_data(1, b"x" * 1000)
    send(server, client)
    c.equal(client.remote_flow_control_window(1), 64535, "after 1000 unacknowledged bytes")


@case("T.R06.28")
def _(c):
    # Line 105: acknowledged data may be returned with WINDOW_UPDATE, never more than acknowledged.
    client, server = request_pair()
    server.send_headers(1, STATUS)
    for _ in range(3):
        server.send_data(1, b"x" * 16384)
    got = send(server, client)
    acknowledged = 0
    for event in events_of(got, "DataReceived"):
        client.acknowledge_received_data(event.flow_controlled_length, 1)
        acknowledged += event.flow_controlled_length
    c.equal(acknowledged, 3 * 16384, "acknowledged bytes")
    before = server.local_flow_control_window(1)
    out = client.data_to_send()
    updates = kind(frames(out), "WindowUpdateFrame")
    c.require(all(f.stream_id in (0, 1) for f in updates), f"WINDOW_UPDATE targets stream 1 or the connection: {updates}")
    stream_total = sum(f.window_increment for f in updates if f.stream_id == 1)
    conn_total = sum(f.window_increment for f in updates if f.stream_id == 0)
    c.require(stream_total <= acknowledged and conn_total <= acknowledged,
              f"increments (stream {stream_total}, connection {conn_total}) do not exceed {acknowledged}")
    server.receive_data(out)
    after = server.local_flow_control_window(1)
    c.require(after in (before + stream_total, min(before + stream_total, before + conn_total)),
              f"server window grows by the increments: {before} -> {after} (stream {stream_total}, conn {conn_total})")


@case("T.R06.29")
def _(c):
    # Line 107: increment_flow_control_window emits WINDOW_UPDATE on the connection or a stream.
    client, server = request_pair()
    client.increment_flow_control_window(1000)
    client.increment_flow_control_window(500, stream_id=1)
    out = client.data_to_send()
    updates = sorted((f.stream_id, f.window_increment) for f in kind(frames(out), "WindowUpdateFrame"))
    c.equal(updates, [(0, 1000), (1, 500)], "WINDOW_UPDATE frames (stream, increment)")
    got = list(server.receive_data(out))
    c.equal(len([e for e in events_of(got, "WindowUpdated") if e.delta == 1000]), 1, "connection WindowUpdated delta 1000")
    one(c, got, "WindowUpdated", stream_id=1, delta=500)


@case("T.R06.34")
def _(c):
    # Line 123: inbound_flow_control_window starts at 65535 and falls with unacknowledged data.
    client, server = request_pair()
    c.equal(client.inbound_flow_control_window, 65535, "initial inbound window")
    server.send_headers(1, STATUS)
    server.send_data(1, b"x" * 1000)
    send(server, client)
    c.equal(client.inbound_flow_control_window, 64535, "after 1000 unacknowledged bytes")


@case("T.integration.flow-control-recovery")
def _(c):
    # Lines 83, 101-107, 123: exhaust a stream window, observe FlowControlError, recover via WINDOW_UPDATE.
    client, server = request_pair()
    server.send_headers(1, STATUS)
    sent = 0
    while server.local_flow_control_window(1) >= 16384 and sent < 10 * 16384:
        server.send_data(1, b"x" * 16384)
        sent += 16384
    c.equal(sent, 3 * 16384, "three full frames fit the default window")
    raises_exactly(c, "FlowControlError", "FrameTooLargeError", lambda: server.send_data(1, b"x" * 16384),
                   "over-window send")
    send(server, client)
    c.equal(client.inbound_flow_control_window, 65535 - sent, "client inbound window fell by the received bytes")
    c.equal(client.remote_flow_control_window(1), 65535 - sent, "client remote window fell by the received bytes")
    before = server.local_flow_control_window(1)
    client.increment_flow_control_window(65535)
    client.increment_flow_control_window(65535, stream_id=1)
    got = send(client, server)
    c.require(events_of(got, "WindowUpdated"), "server receives WindowUpdated")
    one(c, got, "WindowUpdated", stream_id=1, delta=65535)
    c.require(server.local_flow_control_window(1) > before, "server window increased")
    server.send_data(1, b"y" * 16384)
    one(c, send(server, client), "DataReceived", stream_id=1, data=b"y" * 16384)


# ============================================================================ stream-control-frames

@case("T.R06.19")
def _(c):
    # Line 91: reset_stream emits RST_STREAM; default error code 0.
    client, server = pair()
    client.send_headers(1, REQ)
    client.send_headers(3, REQ)
    send(client, server)
    client.reset_stream(1)
    client.reset_stream(3, error_code=h2().errors.ErrorCodes.CANCEL)
    out = client.data_to_send()
    c.equal(sorted((f.stream_id, f.error_code) for f in kind(frames(out), "RstStreamFrame")), [(1, 0), (3, 8)],
            "RST_STREAM (stream, error code)")
    got = list(server.receive_data(out))
    for stream_id, code in ((1, 0), (3, 8)):
        c.equal(one(c, got, "StreamReset", stream_id=stream_id).error_code, code, f"StreamReset({stream_id}).error_code")


@case("T.R06.20")
def _(c):
    # Line 93: push_stream emits PUSH_PROMISE; the client sees PushedStreamReceived.
    from hpack import Decoder
    client, server = request_pair()
    push_id = server.get_next_available_stream_id()
    c.equal(push_id, 2, "server push id")
    server.push_stream(1, push_id, PUSH)
    out = server.data_to_send()
    parsed = frames(out)
    promises = kind(parsed, "PushPromiseFrame")
    c.equal([(f.stream_id, f.promised_stream_id) for f in promises], [(1, 2)], "PUSH_PROMISE on 1 promising 2")
    c.equal(header_blocks(parsed, Decoder())[0][1], PUSH, "promised headers")
    pushed = one(c, list(client.receive_data(out)), "PushedStreamReceived")
    c.equal((pushed.parent_stream_id, pushed.pushed_stream_id), (1, 2), "PushedStreamReceived ids")
    c.equal([tuple(h) for h in pushed.headers], as_bytes(PUSH), "PushedStreamReceived headers")


@case("T.R06.21")
def _(c):
    # Line 93: no PUSH_PROMISE once the client set ENABLE_PUSH=0.
    client, server = pair()
    client.update_settings({h2().settings.SettingCodes.ENABLE_PUSH: 0})
    send(client, server)
    client.send_headers(1, REQ, end_stream=True)
    send(client, server)
    server.data_to_send()
    c.raises(exc("ProtocolError"), lambda: server.push_stream(1, 2, PUSH), "push after ENABLE_PUSH=0")
    c.equal(kind(frames(server.data_to_send()), "PushPromiseFrame"), [], "no PUSH_PROMISE emitted")


@case("T.R06.22")
def _(c):
    # Line 95: close_connection emits GOAWAY; the peer sees ConnectionTerminated.
    codes = h2().errors.ErrorCodes
    for kwargs, code in (({}, 0), ({"error_code": codes.PROTOCOL_ERROR, "last_stream_id": 5}, 1)):
        client, server = request_pair()
        server.close_connection(**kwargs)
        out = server.data_to_send()
        goaway = kind(frames(out), "GoAwayFrame")
        c.equal([f.error_code for f in goaway], [code], f"GOAWAY error code for {kwargs}")
        term = one(c, list(client.receive_data(out)), "ConnectionTerminated")
        c.equal(term.error_code, code, "ConnectionTerminated.error_code")
        if "last_stream_id" in kwargs:
            c.equal(goaway[0].last_stream_id, 5, "GOAWAY last_stream_id")
            c.equal(term.last_stream_id, 5, "ConnectionTerminated.last_stream_id")


@case("T.R06.23")
def _(c):
    # Line 95: a connection that received GOAWAY rejects new streams.
    client, server = request_pair()
    server.close_connection()
    send(server, client)
    raises_h2_error(c, lambda: client.send_headers(client.get_next_available_stream_id(), REQ), "new stream after GOAWAY")


@case("T.R06.24")
def _(c):
    # Line 97: prioritize emits PRIORITY; the peer sees PriorityUpdated (weight 1-256, default 16, root 0).
    client, server = pair()
    client.send_headers(1, REQ)
    client.send_headers(3, REQ)
    send(client, server)
    client.prioritize(3, weight=32, depends_on=1, exclusive=True)
    client.prioritize(1)
    out = client.data_to_send()
    by_stream = {f.stream_id: f for f in kind(frames(out), "PriorityFrame")}
    c.equal(sorted(by_stream), [1, 3], "PRIORITY frames for streams 1 and 3")
    c.equal((by_stream[3].stream_weight + 1, by_stream[3].depends_on, by_stream[3].exclusive), (32, 1, True),
            "PRIORITY frame for stream 3 (weight, depends_on, exclusive)")
    got = list(server.receive_data(out))
    one(c, got, "PriorityUpdated", stream_id=3, weight=32, depends_on=1, exclusive=True)
    one(c, got, "PriorityUpdated", stream_id=1, weight=16, depends_on=0)


@case("T.R06.31")
def _(c):
    # Line 113: ping is answered automatically with a PING ACK carrying the same data.
    client, server = pair()
    client.ping(b"12345678")
    out = client.data_to_send()
    c.equal([(f.opaque_data, "ACK" in f.flags) for f in kind(frames(out), "PingFrame")], [(b"12345678", False)],
            "PING frame")
    one(c, list(server.receive_data(out)), "PingReceived", ping_data=b"12345678")
    out = server.data_to_send()
    c.require(any("ACK" in f.flags and f.opaque_data == b"12345678" for f in kind(frames(out), "PingFrame")),
              "server queued the PING ACK automatically")
    one(c, list(client.receive_data(out)), "PingAckReceived", ping_data=b"12345678")


@case("T.R06.32")
def _(c):
    # Line 117: ALTSVC frames on stream 0 (None) and on a stream; the peer sees AlternativeServiceAvailable.
    client, server = request_pair()
    server.advertise_alternative_service(b'h2=":8000"')
    server.advertise_alternative_service(b'h2=":8000"', stream_id=1)
    out = server.data_to_send()
    c.equal(sorted((f.stream_id, bytes(f.field)) for f in kind(frames(out), "AltSvcFrame")),
            [(0, b'h2=":8000"'), (1, b'h2=":8000"')], "ALTSVC frames (stream, field)")
    got = events_of(list(client.receive_data(out)), "AlternativeServiceAvailable")
    c.equal([e.field_value for e in got], [b'h2=":8000"'] * 2, "AlternativeServiceAvailable field values")


@case("T.integration.stream-termination")
def _(c):
    # Lines 83-95, 121-122: end, reset and shut down streams and the connection.
    codes = h2().errors.ErrorCodes
    client, server = pair()
    for stream_id in (1, 3, 5):
        client.send_headers(stream_id, REQ)
    send(client, server)
    client.end_stream(1)
    one(c, send(client, server), "StreamEnded", stream_id=1)
    server.send_headers(1, STATUS, end_stream=True)
    send(server, client)
    client.reset_stream(3, error_code=codes.CANCEL)
    c.equal(one(c, send(client, server), "StreamReset", stream_id=3).error_code, 8, "StreamReset(3).error_code")
    c.equal((client.open_outbound_streams, server.open_inbound_streams), (1, 1), "only stream 5 remains open")
    server.close_connection(codes.NO_ERROR, last_stream_id=5)
    term = one(c, send(server, client), "ConnectionTerminated")
    c.equal((term.error_code, term.last_stream_id), (0, 5), "ConnectionTerminated")
    c.raises(exc("ProtocolError"), lambda: client.send_data(1, b"x"), "send_data on closed stream 1")
    raises_h2_error(c, lambda: client.send_headers(7, REQ), "opening stream 7 after GOAWAY")


@case("T.integration.control-frames")
def _(c):
    # Lines 93-117: ping, push, priority and ALTSVC on one pair; push refused when disabled.
    client, server = request_pair()
    client.ping(b"abcdefgh")
    one(c, send(client, server), "PingReceived", ping_data=b"abcdefgh")
    one(c, send(server, client), "PingAckReceived", ping_data=b"abcdefgh")
    server.push_stream(1, 2, PUSH)
    one(c, send(server, client), "PushedStreamReceived", parent_stream_id=1, pushed_stream_id=2)
    client.prioritize(1, weight=64)
    one(c, send(client, server), "PriorityUpdated", stream_id=1, weight=64)
    server.advertise_alternative_service(b'h2=":8000"')
    one(c, send(server, client), "AlternativeServiceAvailable", field_value=b'h2=":8000"')
    client, server = pair()
    client.update_settings({h2().settings.SettingCodes.ENABLE_PUSH: 0})
    send(client, server)
    client.send_headers(1, REQ, end_stream=True)
    send(client, server)
    c.raises(exc("ProtocolError"), lambda: server.push_stream(1, 2, PUSH), "push after ENABLE_PUSH=0")


# ============================================================================ settings-upgrade

def decode_upgrade(c, value):
    c.require(isinstance(value, bytes), f"upgrade value is bytes, got {type(value).__name__}")
    c.require(re.fullmatch(rb"[A-Za-z0-9_-]*={0,2}", value) is not None, f"base64url alphabet: {value[:60]!r}")
    stripped = value.rstrip(b"=")
    payload = base64.urlsafe_b64decode(stripped + b"=" * (-len(stripped) % 4))
    c.equal(len(payload) % 6, 0, "SETTINGS payload is 6-byte entries")
    return {int.from_bytes(payload[i:i + 2], "big"): int.from_bytes(payload[i + 2:i + 6], "big")
            for i in range(0, len(payload), 6)}


@case("T.R06.03")
def _(c):
    # Line 70: client upgrade returns base64url settings, queues the preface, stream 1 is open.
    client = conn(True)
    entries = decode_upgrade(c, client.initiate_upgrade_connection())
    for name, value in DEFAULTS.items():
        if SETTING_INTS[name] in entries:
            c.equal(entries[SETTING_INTS[name]], value, f"upgrade settings carry the client's {name}")
    parsed = frames(client.data_to_send(), magic=True)
    c.require(parsed and type(parsed[0]).__name__ == "SettingsFrame", "connection preface queued (magic + SETTINGS)")
    c.require(isinstance(client.local_flow_control_window(1), int), "stream 1 exists after the upgrade")


@case("T.R06.04")
def _(c):
    # Line 71: server accepts the settings header; stream 1 is open for the response.
    client = conn(True)
    server = conn(False)
    server.initiate_upgrade_connection(settings_header=client.initiate_upgrade_connection())
    server.send_headers(1, STATUS)
    c.equal([f.stream_id for f in kind(frames(server.data_to_send()), "HeadersFrame")], [1], "response HEADERS on stream 1")
    from hyperframe.frame import SettingsFrame
    payload = SettingsFrame(0, settings={3: 10, 4: 100}).serialize_body()
    server = conn(False)
    server.initiate_upgrade_connection(settings_header=base64.urlsafe_b64encode(payload).rstrip(b"="))
    server.send_headers(1, STATUS)
    c.equal(server.local_flow_control_window(1), 100, "hand-built INITIAL_WINDOW_SIZE=100 adopted for stream 1")
    raises_exactly(c, "FlowControlError", "FrameTooLargeError", lambda: server.send_data(1, b"x" * 101),
                   "101 bytes against the adopted 100-byte window")


@case("T.R06.11")
def _(c):
    # Line 81: TooManyStreamsError beyond the peer's MAX_CONCURRENT_STREAMS.
    client, server = pair()
    server.update_settings({h2().settings.SettingCodes.MAX_CONCURRENT_STREAMS: 1})
    settle(client, server)
    client.send_headers(1, REQ)
    c.raises(exc("TooManyStreamsError"), lambda: client.send_headers(3, REQ), "second concurrent stream")


@case("T.R06.30")
def _(c):
    # Line 111: update_settings sends SETTINGS; the peer sees RemoteSettingsChanged.
    client, server = pair()
    client.update_settings({h2().settings.SettingCodes.MAX_CONCURRENT_STREAMS: 50})
    out = client.data_to_send()
    sent = [f for f in kind(frames(out), "SettingsFrame") if "ACK" not in f.flags]
    c.equal([f.settings.get(3) for f in sent], [50], "non-ACK SETTINGS with MAX_CONCURRENT_STREAMS=50")
    event = one(c, list(server.receive_data(out)), "RemoteSettingsChanged")
    c.equal(changed(event, "MAX_CONCURRENT_STREAMS").new_value, 50, "RemoteSettingsChanged new_value")


@case("T.integration.settings-negotiation")
def _(c):
    # Lines 73, 81, 111, 186-188: preface settings, acknowledgement and enforcement.
    client, server = conn(True), conn(False)
    client.initiate_connection()
    client.data_to_send()
    server.initiate_connection()
    got = list(server.receive_data(MAGIC + settings_frame(DEFAULTS)))
    event = one(c, got, "RemoteSettingsChanged")
    for name, value in DEFAULTS.items():
        c.equal((changed(event, name).original_value, changed(event, name).new_value), (value, value),
                f"handshake {name}")
    send(server, client)
    server.update_settings({h2().settings.SettingCodes.MAX_CONCURRENT_STREAMS: 1})
    got = send(server, client)
    c.equal(changed(one(c, got, "RemoteSettingsChanged"), "MAX_CONCURRENT_STREAMS").new_value, 1,
            "client sees MAX_CONCURRENT_STREAMS=1")
    c.require(events_of(send(client, server), "SettingsAcknowledged"), "server receives SettingsAcknowledged")
    client.send_headers(1, REQ)
    c.raises(exc("TooManyStreamsError"), lambda: client.send_headers(3, REQ), "second concurrent stream")
    peer = conn(False)
    peer.initiate_connection()
    got = list(peer.receive_data(MAGIC + settings_frame({"MAX_CONCURRENT_STREAMS": 200})))
    c.equal(changed(one(c, got, "RemoteSettingsChanged"), "MAX_CONCURRENT_STREAMS").new_value, 200,
            "200 reported as advertised")


@case("T.integration.upgrade")
def _(c):
    # Lines 69-71: HTTP/1.1 upgrade answered on stream 1.
    client, server = conn(True), conn(False)
    value = client.initiate_upgrade_connection()
    decode_upgrade(c, value)
    server.initiate_upgrade_connection(settings_header=value)
    server.send_headers(1, STATUS)
    server.send_data(1, b"ok", end_stream=True)
    to_server = client.data_to_send()
    c.require(to_server.startswith(MAGIC), "client queued the preface")
    server.receive_data(to_server)
    got = send(server, client)
    in_order(c, got, [("ResponseReceived", {"stream_id": 1}), ("DataReceived", {"stream_id": 1, "data": b"ok"}),
                      ("StreamEnded", {"stream_id": 1})], "client events on stream 1")
    c.equal(client.get_next_available_stream_id(), 3, "next client stream id after the upgrade")
