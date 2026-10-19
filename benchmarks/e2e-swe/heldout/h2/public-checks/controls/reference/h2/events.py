class Event:
    fields = ()

    def __init__(self, **values):
        for name in self.fields:
            setattr(self, name, values.get(name))

    def __repr__(self):
        body = ", ".join(f"{name}={getattr(self, name)!r}" for name in self.fields)
        return f"<{type(self).__name__} {body}>"


class RequestReceived(Event):
    fields = ("stream_id", "headers", "stream_ended", "priority_updated")


class ResponseReceived(Event):
    fields = ("stream_id", "headers", "stream_ended", "priority_updated")


class TrailersReceived(Event):
    fields = ("stream_id", "headers", "stream_ended", "priority_updated")


class DataReceived(Event):
    fields = ("stream_id", "data", "flow_controlled_length", "stream_ended")


class StreamEnded(Event):
    fields = ("stream_id",)


class StreamReset(Event):
    fields = ("stream_id", "error_code", "remote_reset")


class RemoteSettingsChanged(Event):
    fields = ("changed_settings",)


class SettingsAcknowledged(Event):
    fields = ("changed_settings",)


class WindowUpdated(Event):
    fields = ("stream_id", "delta")


class PingReceived(Event):
    fields = ("ping_data",)


class PingAckReceived(Event):
    fields = ("ping_data",)


class PushedStreamReceived(Event):
    fields = ("parent_stream_id", "pushed_stream_id", "headers")


class ConnectionTerminated(Event):
    fields = ("error_code", "last_stream_id", "additional_data")


class PriorityUpdated(Event):
    fields = ("stream_id", "weight", "depends_on", "exclusive")


class AlternativeServiceAvailable(Event):
    fields = ("origin", "field_value")
