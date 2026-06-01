"""Decorators for marking Python classes and methods as AuraGrid remotable services.

These decorators mirror the C# [AuraGridService] and [AuraGridMethod] attributes,
allowing Python MAS developers to define services that integrate with AuraGrid's
remoting pipeline (gRPC + OpenAPI auto-generation).

Usage::

    @auragrid_service(name="Calculator", description="Arithmetic operations")
    class CalculatorService:

        @auragrid_method(description="Adds two integers")
        def add(self, a: int, b: int) -> int:
            return a + b
"""

from __future__ import annotations

from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


def auragrid_service(
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Callable[[type[T]], type[T]]:
    """Class decorator that marks a class as an AuraGrid remotable service.

    Args:
        name: Override the service name (defaults to class name).
        description: Human-readable description of the service.

    The decorator stores metadata in ``cls._auragrid_service_meta``.
    """

    def decorator(cls: type[T]) -> type[T]:
        cls._auragrid_service_meta = {  # type: ignore[attr-defined]
            "name": name or cls.__name__,
            "description": description,
        }
        return cls

    return decorator


def auragrid_method(
    name: Optional[str] = None,
    description: Optional[str] = None,
    required_role: Optional[str] = None,
) -> Callable[[F], F]:
    """Method decorator that marks a method as an AuraGrid remotable operation.

    Args:
        name: Override the method name (defaults to function name).
        description: Human-readable description of the method.
        required_role: Optional GridRole required to invoke this method.
    """

    def decorator(func: F) -> F:
        func._auragrid_method_meta = {  # type: ignore[attr-defined]
            "name": name or func.__name__,
            "description": description,
            "required_role": required_role,
        }
        return func

    return decorator
