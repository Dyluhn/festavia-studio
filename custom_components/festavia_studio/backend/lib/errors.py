"""Safe protocol errors with no remote bodies or credentials."""


class AuthenticationError(RuntimeError):
    def __init__(self, source):
        self.source = source
        super().__init__(f"{source} authorization was rejected")


class CertificateError(RuntimeError):
    def __init__(self, source):
        self.source = source
        super().__init__(f"{source} certificate changed; verify it in Reconfigure")


class RecoveryPending(RuntimeError):
    """The captured installation must be restored before changing ownership."""


class PlaybackBlocked(ValueError):
    """A known playback precondition, identified without remote response text."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)
