"""One application boundary for strict requests and verified caller bindings."""
from .commands import Request
from .results import Result
from .registry import Registry
from .ports.authorization import AuthorizationPort
from ..domain.shared.errors import Forbidden, OrbeHelmError


class Application:
    def __init__(self, registry: Registry, authorization: AuthorizationPort):
        self.registry = registry
        self.authorization = authorization

    def handle(self, request: Request, binding: str) -> Result:
        try:
            if type(request.api_version) is not int or request.api_version != 1:
                raise OrbeHelmError('Unsupported application API version')
            context = self.authorization.verify(binding)
            if context.scope.role not in {'operator', 'agent'} or not context.scope.principal_id:
                raise Forbidden('Access denied')
            operation = self.registry.get(request.operation)
            if operation is None:
                raise OrbeHelmError('Unknown application operation: ' + str(request.operation))
            fields = {**operation.required, **operation.optional}
            if set(operation.required) - set(request.payload) or set(request.payload) - set(fields):
                raise OrbeHelmError('Invalid operation fields')
            for key, value in request.payload.items():
                if type(value) is not fields[key]:
                    raise OrbeHelmError('Invalid operation field: ' + key)
            value = operation.handler(request, context)
            return Result(True, value=value, request_id=request.request_id)
        except OrbeHelmError as error:
            return Result(False, code=error.code, message=str(error), request_id=request.request_id)
        except Exception:
            return Result(False, code='internal_error', message='Application operation failed',
                          request_id=request.request_id)
