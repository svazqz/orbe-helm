"""Pure definition composition behind the shared application request contract."""
from ..registry import Operation
from ...domain.definitions.composition import compose
from ...domain.shared.errors import OrbeHelmError


def compose_definition(request, context):
    instructions = request.payload['instructions']
    for item in instructions:
        if (not isinstance(item, dict) or set(item) - {'path', 'content', 'structured'}
                or not isinstance(item.get('path'), str) or not isinstance(item.get('content'), str)
                or ('structured' in item and type(item['structured']) is not bool)):
            raise OrbeHelmError('Invalid instruction layer')
    return compose(instructions)


def register(registry):
    registry.register(Operation('definitions.compose', compose_definition, {'instructions': list}, {}))
