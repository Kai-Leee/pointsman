"""Sans-I/O HTTP/2 connection: bytes in through receive_data(), bytes out through data_to_send()."""
import base64

import hpack
from hyperframe.frame import (AltSvcFrame, DataFrame, ExtensionFrame, Frame, GoAwayFrame, HeadersFrame,
                              PingFrame, PriorityFrame, PushPromiseFrame, RstStreamFrame, SettingsFrame,
                              WindowUpdateFrame)

from h2 import events as ev
import h2.exceptions as exc
from h2.config import H2Configuration
from h2.settings import ChangedSetting, SettingCodes

MAGIC = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
IWS = SettingCodes.INITIAL_WINDOW_SIZE
DEFAULTS = {SettingCodes.HEADER_TABLE_SIZE: 4096, SettingCodes.MAX_CONCURRENT_STREAMS: 100,
            SettingCodes.INITIAL_WINDOW_SIZE: 65535, SettingCodes.MAX_FRAME_SIZE: 16384}


def _code(code):
    try:
        return SettingCodes(code)
    except ValueError:
        return code


class _Stream:
    def __init__(self, stream_id, outbound, send_window, recv_window):
        self.id = stream_id
        self.outbound = outbound
        self.send_window = send_window
        self.recv_window = recv_window
        self.local_closed = False
        self.remote_closed = False
        self.reset = False
        self.headers_received = False

    @property
    def closed(self):
        return self.reset or (self.local_closed and self.remote_closed)


class H2Connection:
    def __init__(self, config=None):
        self.config = config if config is not None else H2Configuration()
        self.client_side = self.config.client_side
        self.local_settings = dict(DEFAULTS)
        self.remote_settings = dict(DEFAULTS)
        self._pending_settings = []
        self.streams = {}
        self.highest_outbound = 0
        self.highest_inbound = 0
        self.send_window = 65535
        self.inbound_flow_control_window = 65535
        self.goaway_received = False
        self._out = bytearray()
        self._in = bytearray()
        self._preface_needed = not self.client_side
        self._encoder = hpack.Encoder()
        self._decoder = hpack.Decoder()

    # ------------------------------------------------------------------ output buffer
    def _frame(self, frame):
        self._out += frame.serialize()

    def data_to_send(self):
        data, self._out = bytes(self._out), bytearray()
        return data

    def clear_outbound_data_buffer(self):
        self._out.clear()

    # ------------------------------------------------------------------ lifecycle
    def initiate_connection(self):
        if self.client_side:
            self._out += MAGIC
        self._send_settings(dict(self.local_settings))

    def _send_settings(self, settings):
        self._pending_settings.append(settings)
        self._frame(SettingsFrame(0, settings=settings))

    def initiate_upgrade_connection(self, settings_header=None):
        if self.client_side:
            payload = SettingsFrame(0, settings=dict(self.local_settings)).serialize_body()
            self.initiate_connection()
            self._open(1, outbound=True).local_closed = True
            return base64.urlsafe_b64encode(payload).rstrip(b"=")
        if isinstance(settings_header, str):
            settings_header = settings_header.encode("ascii")
        payload = base64.urlsafe_b64decode(settings_header + b"=" * (-len(settings_header) % 4))
        frame = SettingsFrame(0)
        frame.parse_body(memoryview(payload))
        self._apply_remote(frame.settings)
        self.initiate_connection()
        stream = self._open(1, outbound=False)
        stream.remote_closed = stream.headers_received = True
        return None

    # ------------------------------------------------------------------ streams
    def _is_ours(self, stream_id):
        return stream_id % 2 == (1 if self.client_side else 0)

    def _open(self, stream_id, outbound):
        stream = _Stream(stream_id, outbound, self.remote_settings[IWS], self.local_settings[IWS])
        self.streams[stream_id] = stream
        if outbound:
            self.highest_outbound = max(self.highest_outbound, stream_id)
        else:
            self.highest_inbound = max(self.highest_inbound, stream_id)
        return stream

    def _count_open(self, outbound):
        return sum(1 for s in self.streams.values() if s.outbound == outbound and not s.closed)

    @property
    def open_outbound_streams(self):
        return self._count_open(True)

    @property
    def open_inbound_streams(self):
        return self._count_open(False)

    def get_next_available_stream_id(self):
        if self.highest_outbound:
            return self.highest_outbound + 2
        return 1 if self.client_side else 2

    def _sendable(self, stream_id):
        stream = self.streams.get(stream_id)
        if stream is None:
            raise exc.NoSuchStreamError(f"stream {stream_id} does not exist")
        if stream.closed:
            raise exc.StreamClosedError(f"stream {stream_id} is closed")
        if stream.local_closed:
            raise exc.ProtocolError(f"stream {stream_id} send side is closed")
        return stream

    # ------------------------------------------------------------------ sending
    def send_headers(self, stream_id, headers, end_stream=False):
        stream = self.streams.get(stream_id)
        if stream is None:
            if not self._is_ours(stream_id) or stream_id <= self.highest_outbound or not self.client_side:
                raise exc.ProtocolError(f"cannot open stream {stream_id}")
            if self.goaway_received:
                raise exc.ProtocolError("GOAWAY received; no new streams")
            if self.open_outbound_streams >= self.remote_settings[SettingCodes.MAX_CONCURRENT_STREAMS]:
                raise exc.TooManyStreamsError("peer MAX_CONCURRENT_STREAMS reached")
            stream = self._open(stream_id, outbound=True)
        else:
            self._sendable(stream_id)
        flags = ["END_HEADERS"] + (["END_STREAM"] if end_stream else [])
        self._frame(HeadersFrame(stream_id, data=self._encoder.encode(headers), flags=flags))
        if end_stream:
            stream.local_closed = True

    def send_data(self, stream_id, data, end_stream=False):
        stream = self._sendable(stream_id)
        if len(data) > min(stream.send_window, self.send_window):
            raise exc.FlowControlError("data exceeds the flow-control window")
        if len(data) > self.remote_settings[SettingCodes.MAX_FRAME_SIZE]:
            raise exc.FrameTooLargeError("data exceeds MAX_FRAME_SIZE")
        stream.send_window -= len(data)
        self.send_window -= len(data)
        self._frame(DataFrame(stream_id, data=data, flags=["END_STREAM"] if end_stream else []))
        if end_stream:
            stream.local_closed = True

    def end_stream(self, stream_id):
        stream = self._sendable(stream_id)
        self._frame(DataFrame(stream_id, data=b"", flags=["END_STREAM"]))
        stream.local_closed = True

    def reset_stream(self, stream_id, error_code=0):
        stream = self.streams.get(stream_id)
        if stream is None:
            raise exc.NoSuchStreamError(f"cannot reset unknown stream {stream_id}")
        stream.reset = True
        self._frame(RstStreamFrame(stream_id, error_code=error_code))

    def push_stream(self, parent_stream_id, push_stream_id, headers):
        if self.client_side:
            raise exc.ProtocolError("clients cannot push")
        if self.remote_settings.get(SettingCodes.ENABLE_PUSH, 1) == 0:
            raise exc.ProtocolError("peer disabled server push")
        parent = self.streams.get(parent_stream_id)
        if parent is None or parent.closed or parent.local_closed or parent.outbound:
            raise exc.ProtocolError(f"cannot push on stream {parent_stream_id}")
        if not self._is_ours(push_stream_id) or push_stream_id <= self.highest_outbound:
            raise exc.ProtocolError(f"invalid push stream id {push_stream_id}")
        self._open(push_stream_id, outbound=True).remote_closed = True
        self._frame(PushPromiseFrame(parent_stream_id, promised_stream_id=push_stream_id,
                                     data=self._encoder.encode(headers), flags=["END_HEADERS"]))

    def close_connection(self, error_code=0, last_stream_id=None):
        if last_stream_id is None:
            last_stream_id = self.highest_inbound
        self._frame(GoAwayFrame(0, last_stream_id=last_stream_id, error_code=error_code))

    def prioritize(self, stream_id, weight=None, depends_on=None, exclusive=None):
        self._frame(PriorityFrame(stream_id, depends_on=depends_on or 0,
                                  stream_weight=(16 if weight is None else weight) - 1, exclusive=bool(exclusive)))

    def update_settings(self, new_settings):
        self._send_settings(dict(new_settings))

    def ping(self, opaque_data):
        self._frame(PingFrame(0, opaque_data=opaque_data))

    def advertise_alternative_service(self, field_value, stream_id=None):
        self._frame(AltSvcFrame(stream_id or 0, origin=b"", field=field_value))

    # ------------------------------------------------------------------ flow control
    def local_flow_control_window(self, stream_id):
        stream = self.streams.get(stream_id)
        if stream is None:
            raise exc.NoSuchStreamError(f"no local window: stream {stream_id} unknown")
        return min(stream.send_window, self.send_window)

    def remote_flow_control_window(self, stream_id):
        stream = self.streams.get(stream_id)
        if stream is None:
            raise exc.NoSuchStreamError(f"no remote window: stream {stream_id} unknown")
        return stream.recv_window

    def acknowledge_received_data(self, size, stream_id):
        increment = size
        if increment <= 0:
            return
        self.increment_flow_control_window(increment)
        stream = self.streams.get(stream_id)
        if stream is not None and not stream.closed:
            self.increment_flow_control_window(increment, stream_id=stream_id)

    def increment_flow_control_window(self, increment, stream_id=None):
        if stream_id is None or stream_id == 0:
            self.inbound_flow_control_window += increment
            self._frame(WindowUpdateFrame(0, window_increment=increment))
            return
        stream = self.streams.get(stream_id)
        if stream is None:
            raise exc.NoSuchStreamError(f"cannot increment unknown stream {stream_id}")
        stream.recv_window += increment
        self._frame(WindowUpdateFrame(stream_id, window_increment=increment))

    # ------------------------------------------------------------------ receiving
    def receive_data(self, data):
        self._in += data
        if self._preface_needed:
            if len(self._in) < len(MAGIC):
                if not MAGIC.startswith(bytes(self._in)):
                    raise exc.ProtocolError("invalid connection preface")
                return []
            if bytes(self._in[:len(MAGIC)]) != MAGIC:
                raise exc.ProtocolError("invalid connection preface")
            del self._in[:len(MAGIC)]
            self._preface_needed = False
        events = []
        while len(self._in) >= 9:
            frame, length = Frame.parse_frame_header(memoryview(bytes(self._in[:9])))
            if len(self._in) < 9 + length:
                break
            frame.parse_body(memoryview(bytes(self._in[9:9 + length])))
            del self._in[:9 + length]
            events.extend(self._handle(frame))
        return events

    def _handle(self, frame):
        handler = {SettingsFrame: self._on_settings, HeadersFrame: self._on_headers, DataFrame: self._on_data,
                   RstStreamFrame: self._on_rst, PushPromiseFrame: self._on_push, GoAwayFrame: self._on_goaway,
                   WindowUpdateFrame: self._on_window, PriorityFrame: self._on_priority, PingFrame: self._on_ping,
                   AltSvcFrame: self._on_altsvc}.get(type(frame))
        if handler is None:
            if isinstance(frame, ExtensionFrame):
                return []
            # ponytail: no CONTINUATION reassembly; header blocks must fit one frame.
            raise exc.ProtocolError(f"unsupported frame {type(frame).__name__}")
        return handler(frame)

    def _decode(self, block):
        pairs = self._decoder.decode(block, raw=True)
        encoding = self.config.header_encoding
        if encoding:
            return [(bytes(n).decode(encoding), bytes(v).decode(encoding)) for n, v in pairs]
        return [(bytes(n), bytes(v)) for n, v in pairs]

    def _end_remote(self, stream, event, flags):
        if "END_STREAM" not in flags:
            return [event]
        stream.remote_closed = True
        ended = ev.StreamEnded(stream_id=stream.id)
        event.stream_ended = ended
        return [event, ended]

    def _on_settings(self, frame):
        if "ACK" in frame.flags:
            applied = self._pending_settings.pop(0) if self._pending_settings else {}
            changed = {}
            for code, value in applied.items():
                code = _code(code)
                old = self.local_settings.get(code)
                changed[code] = ChangedSetting(code, old, value)
                if code == IWS:
                    for stream in self.streams.values():
                        stream.recv_window += value - old
                self.local_settings[code] = value
            return [ev.SettingsAcknowledged(changed_settings=changed)]
        changed = self._apply_remote(frame.settings)
        self._frame(SettingsFrame(0, flags=["ACK"]))
        return [ev.RemoteSettingsChanged(changed_settings=changed)]

    def _apply_remote(self, settings):
        changed = {}
        for code, value in settings.items():
            code = _code(code)
            changed[code] = ChangedSetting(code, self.remote_settings.get(code), value)
            if code == IWS:
                for stream in self.streams.values():
                    stream.send_window += value - self.remote_settings[IWS]
            elif code == SettingCodes.HEADER_TABLE_SIZE:
                self._encoder.header_table_size = value
            self.remote_settings[code] = value
        return changed

    def _on_headers(self, frame):
        headers = self._decode(frame.data)
        stream = self.streams.get(frame.stream_id)
        if stream is None:
            if self.client_side or self._is_ours(frame.stream_id):
                raise exc.ProtocolError(f"peer cannot open stream {frame.stream_id}")
            stream = self._open(frame.stream_id, outbound=False)
        elif stream.closed:
            return []
        if stream.headers_received:
            cls = ev.TrailersReceived
        else:
            cls = ev.ResponseReceived if self.client_side else ev.RequestReceived
        stream.headers_received = True
        return self._end_remote(stream, cls(stream_id=frame.stream_id, headers=headers), frame.flags)

    def _on_data(self, frame):
        stream = self.streams.get(frame.stream_id)
        if stream is None:
            raise exc.ProtocolError(f"DATA on unknown stream {frame.stream_id}")
        length = frame.flow_controlled_length
        self.inbound_flow_control_window -= length
        stream.recv_window -= length
        if stream.closed:
            return []
        event = ev.DataReceived(stream_id=frame.stream_id, data=frame.data, flow_controlled_length=length)
        return self._end_remote(stream, event, frame.flags)

    def _on_rst(self, frame):
        stream = self.streams.get(frame.stream_id)
        if stream is not None:
            stream.reset = True
        return [ev.StreamReset(stream_id=frame.stream_id, error_code=frame.error_code, remote_reset=True)]

    def _on_push(self, frame):
        headers = self._decode(frame.data)
        self._open(frame.promised_stream_id, outbound=False).local_closed = True
        return [ev.PushedStreamReceived(parent_stream_id=frame.stream_id, pushed_stream_id=frame.promised_stream_id,
                                        headers=headers)]

    def _on_goaway(self, frame):
        self.goaway_received = True
        return [ev.ConnectionTerminated(error_code=frame.error_code, last_stream_id=frame.last_stream_id,
                                        additional_data=frame.additional_data or None)]

    def _on_window(self, frame):
        if frame.stream_id == 0:
            self.send_window += frame.window_increment
        elif frame.stream_id in self.streams:
            self.streams[frame.stream_id].send_window += frame.window_increment
        return [ev.WindowUpdated(stream_id=frame.stream_id, delta=frame.window_increment)]

    def _on_priority(self, frame):
        return [ev.PriorityUpdated(stream_id=frame.stream_id, weight=frame.stream_weight + 1,
                                   depends_on=frame.depends_on, exclusive=frame.exclusive)]

    def _on_ping(self, frame):
        if "ACK" in frame.flags:
            return [ev.PingAckReceived(ping_data=frame.opaque_data)]
        self._frame(PingFrame(0, opaque_data=frame.opaque_data, flags=["ACK"]))
        return [ev.PingReceived(ping_data=frame.opaque_data)]

    def _on_altsvc(self, frame):
        altsvc_events = [ev.AlternativeServiceAvailable(origin=frame.origin or None, field_value=frame.field)]
        return altsvc_events
