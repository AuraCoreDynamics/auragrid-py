"""Generates AuraGrid service descriptors from decorated Python classes.

The output matches the ``ServiceDescriptor`` JSON schema consumed by
``PythonServiceDescriptorLoader`` on the C# side.

Usage::

    from auragrid import auragrid_service, auragrid_method, save_descriptor

    @auragrid_service(name="Calculator")
    class CalculatorService:
        @auragrid_method()
        def add(self, a: int, b: int) -> int:
            return a + b

    save_descriptor(CalculatorService)
"""

from __future__ import annotations

import inspect
import json
from typing import Any, get_type_hints

from .type_mapping import map_python_type


def generate_descriptor(cls: type) -> dict[str, Any]:
    """Inspect a ``@auragrid_service`` decorated class and return a ServiceDescriptor dict.

    Args:
        cls: A class decorated with ``@auragrid_service``.

    Returns:
        A dictionary matching the ``ServiceDescriptor`` JSON schema.

    Raises:
        ValueError: If the class is not decorated with ``@auragrid_service``.
    """
    meta = getattr(cls, "_auragrid_service_meta", None)
    if meta is None:
        raise ValueError(
            f"Class {cls.__name__} is not decorated with @auragrid_service"
        )

    hints = get_type_hints(cls)
    methods: list[dict[str, Any]] = []

    for name, func in inspect.getmembers(cls, predicate=inspect.isfunction):
        method_meta = getattr(func, "_auragrid_method_meta", None)
        if method_meta is None:
            continue

        method_hints = get_type_hints(func)
        sig = inspect.signature(func)
        parameters: list[dict[str, Any]] = []

        for param_name, param in sig.parameters.items():
            # Skip 'self'
            if param_name == "self":
                continue

            annotation = method_hints.get(param_name, str)
            type_desc = map_python_type(annotation)

            parameters.append(
                {
                    "name": param_name,
                    "type": type_desc,
                    "isOptional": param.default is not inspect.Parameter.empty,
                }
            )

        return_annotation = method_hints.get("return", None)
        return_type = map_python_type(return_annotation)

        method_desc: dict[str, Any] = {
            "methodName": method_meta["name"],
            "parameters": parameters,
            "returnType": return_type,
        }
        if method_meta.get("description"):
            method_desc["description"] = method_meta["description"]
        if method_meta.get("required_role"):
            method_desc["requiredRole"] = method_meta["required_role"]

        methods.append(method_desc)

    descriptor: dict[str, Any] = {
        "serviceName": meta["name"],
        "sourceTypeName": f"{cls.__module__}.{cls.__qualname__}",
        "methods": methods,
    }
    if meta.get("description"):
        descriptor["description"] = meta["description"]

    return descriptor


def save_descriptor(
    cls: type,
    output_path: str = "service-descriptor.json",
) -> None:
    """Generate and write a ``service-descriptor.json`` file for a decorated class.

    Args:
        cls: A class decorated with ``@auragrid_service``.
        output_path: File path to write the JSON descriptor to.
    """
    descriptor = generate_descriptor(cls)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(descriptor, f, indent=4, ensure_ascii=False)
