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

import re


class HopsworksApigenError(Exception):
    """Hopsworks exception related to the management of the Hopsworks public API.

    This exception happens only if there is an error in the hopsworks library itself, as it means misconfiguration of the API management utilities.
    """


class HopsworksDeprecationWarning(DeprecationWarning):
    """Hopsworks deprecation warning."""


def generate_deprecation_message(
    name: str,
    *deprecated_by: str,
    available_until: str | None = None,
):
    if available_until and not re.match(r"^\d+\.\d+$", available_until):
        raise HopsworksApigenError(
            "The available_until parameter must be in the format 'major.minor', e.g., '4.0'."
        )
    v = f"version {available_until}" if available_until else "a future release"

    if len(deprecated_by) == 0:
        raise HopsworksApigenError(
            "At least one recommendation must be provided for deprecation warnings."
        )
    if len(deprecated_by) == 1:
        recs = deprecated_by[0]
    elif len(deprecated_by) == 2:
        recs = f"{deprecated_by[0]} or {deprecated_by[1]}"
    else:
        recs = f"{', '.join(deprecated_by[:-1])}, or {deprecated_by[-1]}"

    return (
        f"{name} is deprecated."
        f" The function will be removed in {v} of hopsworks."
        f" Consider using {recs} instead."
    )
