from app.core.exceptions import DomainException


class DocumentNotFoundError(Exception):
    pass

class DocumentAlreadyExistsError(DomainException):
    pass
#crea excepciones personalizadas en pythonn
