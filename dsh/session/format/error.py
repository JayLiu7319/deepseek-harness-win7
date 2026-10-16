"""Errors for lossless Session format admission and adjacent conversion."""


class SessionFormatError(ValueError):
    name = 'SessionFormatError'


class SessionFormatUnsupportedMigrationError(SessionFormatError):
    name = 'SessionFormatUnsupportedMigrationError'
