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

"""Automatic Hopsworks API management."""

from .aliases import also_available_as as also_available_as
from .aliases import public as public
from .deprecation import deprecated as deprecated
from .errors import (
    HopsworksApigenError as HopsworksApigenError,
)
from .errors import (
    HopsworksDeprecationWarning as HopsworksDeprecationWarning,
)
from .errors import (
    generate_deprecation_message as generate_deprecation_message,
)
