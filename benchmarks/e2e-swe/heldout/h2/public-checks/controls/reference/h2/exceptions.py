class H2Error(Exception):
    pass


class ProtocolError(H2Error):
    pass


class FrameTooLargeError(ProtocolError):
    pass


class TooManyStreamsError(ProtocolError):
    pass


class FlowControlError(ProtocolError):
    pass


class NoSuchStreamError(ProtocolError):
    pass


class StreamClosedError(NoSuchStreamError):
    pass
