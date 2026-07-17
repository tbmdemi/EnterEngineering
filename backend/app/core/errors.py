class AppError(Exception):
    def __init__(self, code, message, details=None, status_code=400):
        self.status_code = status_code
        self.payload = {"code": code, "message": message, "details": details or {}}
        super().__init__(message)
