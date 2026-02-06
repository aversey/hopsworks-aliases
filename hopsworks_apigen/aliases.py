#
#   Copyright 2026 Hopsworks AB
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

from __future__ import annotations

from typing import Callable, TypeVar, overload


class PublicNames:
    nameOf: dict[object, str] = {}


T = TypeVar("T")

@overload
def public(*paths: str, order: int = 0) -> Callable[[T], T]: ...
@overload
def public(symbol: T, /) -> T: ...
def public(*paths: str | T, order: int = 0) -> Callable[[T], T] | T:
    """Make a function or class publicly available, possibly via an alias.

    The first path (or the original path, if no paths are given) becomes the primary public import path.
    Only the primary public path has a dedicated documentation page in the API reference.
    The other paths still can be used to import the entity, link it in the docs, and are shown in the docs in a special section, in the same order as in the list of paths.

    Empty string in the list of paths means the current path of the entity.

    For each non-empty path given, a corresponding alias is created.

    Example:
        We can publish a function or a class under its current path:
        ```python
        @public
        def function():
            pass

        @public
        class SampleClass:
            pass
        ```

        We can create a public alias for an entity, and make it the primary public path, keeping the original path public as well:
        ```python
        @public("another_module.function", "")
        def function():
            pass
        ```

        Or we can make the entity publicly available only under aliases:
        ```python
        @public(
            "another_module.function",
            "another_module.function_with_another_name",
            "different_module.function",
        )
        def function():
            pass
        ```

        We can control the order in which entities appear on the module page:
        ```python
        @public(order=1)  # appears before entities with lower order
        class ImportantClass:
            pass

        @public # order=0 by default, appears last
        class LessImportantClass:
            pass

        @public # This will be showed before LessImportantClass and after ImportantClass, because each order is sorted alphabetically.
        class AClass:
            pass
        ```

    Parameters:
        paths: The import paths under which the entity is publicly available, empty string means the current path.
        order: Sorting order on the module documentation page. Higher values appear first, then alphabetically within the same order.
    """
    # The real effect takes place in hopsworks-apigen setuptools plugin.
    if len(paths) == 1 and not isinstance(paths[0], str):
        return paths[0]

    def publicate(symbol: T) -> T:
        name = paths[0] if paths else ""
        if not isinstance(name, str):
            raise TypeError(
                "The primary public path must be a string representing an import path."
            )
        PublicNames.nameOf[symbol] = name
        return symbol

    return publicate


def also_available_as(*paths: str):
    """Create internal aliases for a function or a class.

    The entity becomes available under the given internal paths.
    They can be used to import it or link it in the docs.

    Example:
        ```python
        @also_available_as("internal_module.function")
        def function():
            pass
        ```

    Parameters:
        paths: The internal import paths under which the entity is available.
    """
    # The real effect takes place in hopsworks-apigen setuptools plugin.
    return lambda symbol: symbol
