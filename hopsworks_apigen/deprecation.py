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

import functools
import inspect
import warnings

from hopsworks_apigen.aliases import PublicNames
from hopsworks_apigen.errors import (
    HopsworksApigenError,
    HopsworksDeprecationWarning,
    generate_deprecation_message,
)


def deprecated(
    *deprecated_by: str,
    available_until: str | None = None,
    public_name: str | None = None,
):
    """Mark a function or a class as deprecated.

    Use of the entity outside hopsworks will print a warning, saying that it is going to be removed from the public API in one of the future releases.
    Therefore, do not use it on classes or functions used internally; it is a utility for deprecating parts of our public API.

    Note:
        Use `@deprecated` above `@public` for the decorator to automatically infer the public name; like this:
        ```python
        @deprecated("path.to.new_function")
        @public("public.name")
        def old_function():
            pass
        ```

    Parameters:
        deprecated_by: A set of recommendations to use instead, cannot be empty.
        available_until: The first hopsworks release in which the entity will become unavailable, defaults to `None`; if the release is known, it is reported to the external user in the warning.
        public_name: The full qualified public name of the entity; usually should not be given, in which case it is inferred from the entity being deprecated.
    """

    def deprecate(symbol: object):
        name = public_name
        if not name:
            name = PublicNames.nameOf.get(symbol)
        if not name:
            name = symbol.__qualname__

        if inspect.isclass(symbol):
            methods = inspect.getmembers(symbol, predicate=inspect.isfunction)
            for n, m in methods:
                dep = deprecated(
                    *deprecated_by,
                    available_until=available_until,
                    public_name=name + "." + n,
                )
                setattr(symbol, n, dep(m))
            return symbol

        if inspect.isfunction(symbol):
            message = generate_deprecation_message(
                name,
                *deprecated_by,
                available_until=available_until,
            )

            @functools.wraps(symbol)
            def deprecated_f(*args, **kwargs):
                caller = inspect.getmodule(inspect.stack()[1][0])
                cn = caller.__name__ if caller else ""
                if not cn.startswith(("hopsworks", "hsfs", "hsml")):
                    warnings.warn(message, HopsworksDeprecationWarning, 2)
                return symbol(*args, **kwargs)

            return deprecated_f

        raise HopsworksApigenError(
            "Deprecation of something else than class or function."
        )

    return deprecate
