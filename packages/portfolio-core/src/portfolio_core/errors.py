class CoreError(ValueError):
    """A structured input, feasibility, or numerical failure, safe to serialize."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else details

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}
