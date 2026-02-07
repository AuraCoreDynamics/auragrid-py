"""Maps Python type annotations to AuraGrid TypeDescriptor JSON dictionaries.

The output format matches the ``ServiceDescriptor`` JSON schema consumed by
``PythonServiceDescriptorLoader`` on the C# side, ensuring seamless interop
between the Python SDK and the .NET remoting pipeline.
"""

from __future__ import annotations

import typing
import uuid
from datetime import datetime
from typing import Any, Optional, Union

# Python 3.10+ supports ``list[int]`` natively; we also handle ``typing.List[int]``.
_PRIMITIVE_MAP: dict[type, dict[str, Any]] = {
    str: {
        "clrTypeName": "System.String",
        "protoType": "string",
        "openApiType": "string",
    },
    int: {
        "clrTypeName": "System.Int64",
        "protoType": "int64",
        "openApiType": "integer",
        "openApiFormat": "int64",
    },
    float: {
        "clrTypeName": "System.Double",
        "protoType": "double",
        "openApiType": "number",
        "openApiFormat": "double",
    },
    bool: {
        "clrTypeName": "System.Boolean",
        "protoType": "bool",
        "openApiType": "boolean",
    },
    bytes: {
        "clrTypeName": "System.Byte[]",
        "protoType": "bytes",
        "openApiType": "string",
        "openApiFormat": "byte",
    },
    datetime: {
        "clrTypeName": "System.DateTime",
        "protoType": "google.protobuf.Timestamp",
        "openApiType": "string",
        "openApiFormat": "date-time",
    },
    uuid.UUID: {
        "clrTypeName": "System.Guid",
        "protoType": "string",
        "openApiType": "string",
        "openApiFormat": "uuid",
    },
}


def map_python_type(annotation: Any) -> dict[str, Any]:
    """Map a Python type annotation to a TypeDescriptor-compatible dictionary.

    Supports: ``str``, ``int``, ``float``, ``bool``, ``bytes``, ``datetime``,
    ``uuid.UUID``, ``list[T]``, ``Optional[T]``, and ``None`` (void).

    Args:
        annotation: A Python type hint (e.g., ``int``, ``list[str]``, ``None``).

    Returns:
        A dictionary matching the ``TypeDescriptor`` JSON shape:
        ``{clrTypeName, protoType, openApiType, openApiFormat?, isCollection, isVoid, elementType?}``
    """
    # None / NoneType → void
    if annotation is None or annotation is type(None):
        return {
            "clrTypeName": "System.Void",
            "protoType": "",
            "openApiType": "",
            "isCollection": False,
            "isVoid": True,
        }

    # Unwrap Optional[T] → T (Optional[T] is Union[T, None])
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is Union:
        # Filter out NoneType from Union args
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return map_python_type(non_none[0])

    # list[T] or typing.List[T]
    if origin is list:
        if args:
            element = map_python_type(args[0])
        else:
            element = map_python_type(str)  # fallback to str for bare list

        return {
            "clrTypeName": f"{element['clrTypeName']}[]",
            "protoType": f"repeated {element['protoType']}",
            "openApiType": "array",
            "isCollection": True,
            "isVoid": False,
            "elementType": element,
        }

    # Primitive types
    if annotation in _PRIMITIVE_MAP:
        result = {
            **_PRIMITIVE_MAP[annotation],
            "isCollection": False,
            "isVoid": False,
        }
        return result

    # Fallback for unknown types
    return {
        "clrTypeName": "System.Object",
        "protoType": "bytes",
        "openApiType": "object",
        "isCollection": False,
        "isVoid": False,
    }
