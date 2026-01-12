#
#   Copyright 2025 Hopsworks AB
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

"""Scripts for automatic management of aliases."""

from collections import defaultdict
from pathlib import Path

import griffe
from setuptools import Command, Distribution


def _discover_python_modules(root):
    """Discover all Python modules in the root directory.

    Returns a list of module paths relative to root.
    """
    python_files = []

    for py_file in root.rglob("*.py"):
        # Skip files in common non-source directories
        if any(
            part.startswith(".")
            or part in {"__pycache__", "build", "dist", "venv", ".venv"}
            for part in py_file.relative_to(root).parts
        ):
            continue

        python_files.append(py_file.relative_to(root))

    return python_files


def collect_aliases(root):
    """Collect all @public decorators from the source files.

    Returns a dict mapping module paths to lists of (from_module, item_name, metadata) tuples.
    """
    # Load the package using griffe
    loader = griffe.GriffeLoader(search_paths=[str(root)])

    # Discover all Python files
    python_files = _discover_python_modules(root)

    # Collect all top-level packages
    top_level_packages = set()
    for py_file in python_files:
        if len(py_file.parts) > 0:
            top_level_packages.add(py_file.parts[0])

    # Load all top-level packages with submodules
    all_modules_to_scan = []
    for package_name in sorted(top_level_packages):
        try:
            package = loader.load(package_name, submodules=True)
            all_modules_to_scan.append(package)
            all_modules_to_scan.extend(_collect_submodules(package))
        except Exception:
            continue

    # Scan all modules for @public decorators
    aliases_by_module = defaultdict(list)
    for module in all_modules_to_scan:
        _scan_module_for_public_decorators(module, aliases_by_module)

    return dict(aliases_by_module)


def _collect_submodules(obj):
    """Recursively collect all submodules."""
    submodules = []
    for member in obj.members.values():
        if member.kind.value == "module" and not member.is_alias:
            submodules.append(member)
            submodules.extend(_collect_submodules(member))
    return submodules


def _scan_module_for_public_decorators(module, aliases_by_module):
    """Scan a module for @public decorators and collect the metadata."""
    for member_name, member in module.members.items():
        if not hasattr(member, "decorators"):
            continue

        for decorator in member.decorators:
            # Check if this is a @public decorator
            if decorator.callable_path and decorator.callable_path.endswith(".public"):
                # Parse decorator arguments
                metadata = _parse_public_decorator(decorator)
                if metadata and metadata["paths"]:
                    # Store the full path to the decorated object
                    from_module = str(module.canonical_path)

                    for target_module in metadata["paths"]:
                        aliases_by_module[target_module].append(
                            (from_module, member_name, metadata)
                        )


def _parse_public_decorator(decorator):
    """Parse a @public decorator call and extract paths and keyword arguments.

    Returns dict with 'paths', 'as_alias', 'deprecated_by', 'available_until'.
    """
    if not isinstance(decorator.value, griffe.ExprCall):
        return None

    expr = decorator.value

    # Extract positional arguments (paths)
    paths = []
    for arg in expr.arguments:
        if isinstance(arg, str):
            # It's a string literal
            paths.append(arg.strip("'\""))
        elif hasattr(arg, "name"):
            # It's an ExprKeyword, skip it
            pass

    # Extract keyword arguments
    kwargs: dict[str, str | set[str] | None] = {
        "as_alias": None,
        "deprecated_by": None,
        "available_until": None,
    }

    for arg in expr.arguments:
        if isinstance(arg, griffe.ExprKeyword):
            key = arg.name
            value = arg.value

            # Convert the value to a Python object
            if isinstance(value, str):
                # String literal
                kwargs[key] = value.strip("'\"")
            elif hasattr(value, "elements"):
                # It's a set/list (ExprSet)
                elements = getattr(value, "elements", [])
                kwargs[key] = {
                    elem.strip("'\"") for elem in elements if isinstance(elem, str)
                }

    return {
        "paths": paths,
        **kwargs,
    }


def collect_managed(root):
    """Generate the content for alias __init__.py files.

    Returns a dict mapping file paths to their generated content.
    """
    managed = {}
    for target_module, alias_list in collect_aliases(root).items():
        # Convert module path to file path
        module_file = root / target_module.replace(".", "/") / "__init__.py"

        # Start with header
        managed[module_file] = "# This file is generated. Do not edit it manually!\n"

        if not alias_list:
            continue

        # Sort for determinism
        alias_list.sort(key=lambda x: (x[0], x[1]))

        imported_modules = set()
        declared_names = set()

        for from_module, item_name, metadata in alias_list:
            # Determine the alias name
            alias_name = metadata["as_alias"] if metadata["as_alias"] else item_name

            # Check for duplicates
            if alias_name in declared_names:
                original_ref = f"{from_module}.{item_name}"
                print(
                    f"Error: {original_ref} is attempted to be exported as {alias_name} "
                    f"in {module_file}, but the package already contains this alias."
                )
                exit(1)

            declared_names.add(alias_name)

            # Import the source module if needed
            if from_module not in imported_modules:
                managed[module_file] += f"import {from_module}\n"
                imported_modules.add(from_module)

            # Build the assignment
            original_ref = f"{from_module}.{item_name}"

            # Wrap with deprecation decorator if needed
            if metadata["deprecated_by"]:
                # Import deprecation helper if not already imported
                if "hopsworks.internal.aliases" not in imported_modules:
                    managed[module_file] += "import hopsworks.internal.aliases\n"
                    imported_modules.add("hopsworks.internal.aliases")

                # Convert deprecated_by to sorted list
                deprecated_by_list = list(metadata["deprecated_by"])
                deprecated_by_list.sort()
                deprecated_by_str = ", ".join(f'"{s}"' for s in deprecated_by_list)

                available_until_str = ""
                if metadata["available_until"]:
                    available_until_str = (
                        f', available_until="{metadata["available_until"]}"'
                    )

                original_ref = (
                    f"hopsworks.internal.aliases.deprecated("
                    f"{deprecated_by_str}{available_until_str})({original_ref})"
                )

            # Add the assignment
            managed[module_file] += f"{alias_name} = {original_ref}\n"

    return managed


def generate_aliases(source_root, destination_root):
    managed = collect_managed(source_root)
    for filepath, content in managed.items():
        filepath: Path
        filepath = destination_root / filepath.relative_to(source_root)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.touch()
        filepath.write_text(content)


class build_aliases(Command):
    def initialize_options(self) -> None:
        self.build_temp: str | None = None
        self.aliases_dir: Path | None = None

    def finalize_options(self) -> None:
        self.set_undefined_options("build", ("build_temp", "build_temp"))
        assert self.build_temp is not None
        self.aliases_dir = Path(self.build_temp) / "aliases"

    def run(self) -> None:
        assert self.aliases_dir is not None

        generate_aliases(Path(), self.aliases_dir)


class install_aliases(Command):
    def initialize_options(self) -> None:
        pass

    def finalize_options(self) -> None:
        pass

    def run(self) -> None:
        pass


def finalize_distribution_options(dist: Distribution) -> None:
    dist.get_command_class("build").sub_commands.append(
        (build_aliases.__name__, None),
    )
    dist.get_command_class("install").sub_commands.append(
        (install_aliases.__name__, None),
    )
