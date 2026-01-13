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

import contextlib
import shutil
from collections import defaultdict
from pathlib import Path

import griffe
from setuptools import Command, Distribution

from hopsworks_aliases import HopsworksAliasesError
from hopsworks_aliases.extension import HopsworksAliases


def _discover_python_modules(root):
    """Discover all Python modules in the root directory.

    Returns a list of module paths relative to root.
    """
    python_files = []

    for py_file in root.rglob("*.py"):
        py_file: Path = py_file.relative_to(root)
        # Skip files in common non-source directories
        if any(
            part.startswith(".") or part in {"__pycache__", "build", "dist", "venv"}
            for part in py_file.parts
        ):
            continue

        if py_file.name == "__init__.py" and py_file.read_text().startswith(
            HopsworksAliases.MAGIC_COMMENT
        ):
            py_file.unlink()
            continue

        python_files.append(py_file)

    return python_files


def collect_aliases(root):
    """Collect all @public decorators from the source files.

    Returns a dict mapping module paths to lists of (from_module, item_name, metadata) tuples.
    """
    # Load the package using griffe
    exts = griffe.Extensions()
    exts.add(HopsworksAliases())
    loader = griffe.GriffeLoader(extensions=exts, search_paths=[str(root)])

    # Discover all Python files
    python_files = _discover_python_modules(root)

    # Collect all top-level packages
    top_level_packages = set()
    for py_file in python_files:
        if len(py_file.parts) > 0:
            top_level_packages.add(py_file.parts[0])

    # Load all top-level packages with submodules
    all_modules_to_scan = set()
    for package_name in sorted(top_level_packages):
        package = loader.load(package_name, submodules=True)
        _collect_with_submodules(package, all_modules_to_scan)

    # Collect aliases
    aliases_by_module = defaultdict(list)
    for module in all_modules_to_scan:
        for member in module.members.values():
            if hasattr(member, "hopsworks_aliases"):
                for alias in member.hopsworks_aliases["aliases"]:
                    for target_module in alias["paths"]:
                        aliases_by_module[target_module].append(alias)

    return dict(aliases_by_module)


def _collect_with_submodules(obj, all_modules_to_scan):
    """Recursively collect all submodules."""
    if obj.kind.value == "module" and not obj.is_alias:
        all_modules_to_scan.add(obj)
        for submodule in obj.members.values():
            _collect_with_submodules(submodule, all_modules_to_scan)


def collect_managed(root):
    """Generate the content for alias __init__.py files.

    Returns a dict mapping file paths to their generated content.
    """
    managed = {}
    for target_module, alias_list in collect_aliases(root).items():
        # Convert module path to file path
        module_file = root / target_module.replace(".", "/") / "__init__.py"

        # Start with header
        managed[module_file] = HopsworksAliases.MAGIC_COMMENT

        # Sort for determinism
        alias_list.sort(key=lambda x: (x["from_module"], x["object_name"]))

        imported_modules = set()
        declared_names = {}

        for alias in alias_list:
            # Determine the alias name
            alias_name = (
                alias["as_alias"] if alias["as_alias"] else alias["object_name"]
            )

            original_ref = f"{alias['from_module']}.{alias['object_name']}"

            # Check for duplicates
            if alias_name in declared_names:
                raise HopsworksAliasesError(
                    f"Error: {original_ref} is attempted to be exported as {alias_name} "
                    f"in {target_module}, but the package already contains this alias, set to {declared_names[alias_name]}."
                )

            declared_names[alias_name] = original_ref

            # Import the source module if needed
            if alias["from_module"] not in imported_modules:
                managed[module_file] += f"import {alias['from_module']}\n"
                imported_modules.add(alias["from_module"])

            # Wrap with deprecation decorator if needed
            if alias["deprecated_by"]:
                # Import deprecation helper if not already imported
                if "hopsworks_aliases" not in imported_modules:
                    managed[module_file] += "import hopsworks_aliases\n"
                    imported_modules.add("hopsworks_aliases")

                # Convert deprecated_by to sorted list
                deprecated_by_list = list(alias["deprecated_by"])
                deprecated_by_list.sort()
                deprecated_by_str = ", ".join(f'"{s}"' for s in deprecated_by_list)

                available_until_str = ""
                if alias["available_until"]:
                    available_until_str = (
                        f', available_until="{alias["available_until"]}"'
                    )

                original_ref = (
                    f"hopsworks_aliases.deprecated("
                    f"{deprecated_by_str}{available_until_str})({original_ref})"
                )

            # Add the assignment
            managed[module_file] += f"{alias_name} = {original_ref}\n"

    return managed


def generate_aliases(source_root, destination_root):
    managed = collect_managed(source_root)
    gitignore_entries = []

    for filepath, content in managed.items():
        filepath: Path
        filepath = destination_root / filepath.relative_to(source_root)

        parent = filepath.parent
        to_be_created = []
        while not parent.exists():
            to_be_created.append(parent)
            parent = parent.parent

        for d in reversed(to_be_created):
            with contextlib.suppress(ValueError):
                rel_path = d.relative_to(destination_root)
                gitignore_entries.append(f"/{rel_path}")
            d.mkdir()
            (d / "__init__.py").touch()

        filepath.write_text(content)

    # Generate single .gitignore at the root
    if gitignore_entries:
        gitignore_path = destination_root / ".gitignore"
        if gitignore_path.exists():
            gitignore_content = gitignore_path.read_text()
        else:
            gitignore_content = "# Ignore generated alias files\n"
        gitignore_content += "".join(str(x) + "\n" for x in sorted(gitignore_entries))
        gitignore_path.write_text(gitignore_content)

    return managed


class build_aliases(Command):
    def initialize_options(self) -> None:
        self.build_temp: str | None = None
        self.aliases_dir: Path | None = None
        self.editable_mode: bool = False

    def finalize_options(self) -> None:
        self.set_undefined_options("build", ("build_temp", "build_temp"))
        assert self.build_temp is not None

        # In editable mode, generate files in place
        # Otherwise, generate in build directory
        if self.editable_mode:
            self.aliases_dir = Path()
        else:
            self.aliases_dir = Path(self.build_temp) / "aliases"

    def run(self) -> None:
        assert self.aliases_dir is not None

        self.managed = generate_aliases(Path(), self.aliases_dir)

    def get_outputs(self) -> list[str]:
        """Return all files that are outputs of this command."""
        assert self.aliases_dir is not None

        # Collect what would be generated without actually generating
        outputs = []

        for filepath in self.managed:
            output_path = self.aliases_dir / filepath.relative_to(Path())
            outputs.append(str(output_path))

        return outputs

    def get_output_mapping(self) -> dict[str, str]:
        """Map destination files to source files."""
        assert self.aliases_dir is not None

        # For each generated file, map it to itself in the destination
        mapping = {}

        for filepath in self.managed:
            output_path = self.aliases_dir / filepath.relative_to(Path())
            mapping[str(output_path)] = str(output_path)

        return mapping


class install_aliases(Command):
    def initialize_options(self) -> None:
        self.aliases_dir: Path | None = None
        self.install_lib: str | None = None

    def finalize_options(self) -> None:
        self.set_undefined_options(
            "build_aliases",
            ("aliases_dir", "aliases_dir"),
        )
        self.set_undefined_options(
            "install",
            ("install_lib", "install_lib"),
        )

    def run(self) -> None:
        assert self.aliases_dir is not None
        assert self.install_lib is not None

        # Copy all generated files from build/aliases to install_lib
        if not self.aliases_dir.exists():
            return

        for src_file in self.aliases_dir.rglob("*.py"):
            rel_path = src_file.relative_to(self.aliases_dir)
            dest_file = Path(self.install_lib) / rel_path

            # Create parent directories if needed
            dest_file.parent.mkdir(parents=True, exist_ok=True)

            # Copy the file
            shutil.copy(src_file, dest_file)


def finalize_distribution_options(dist: Distribution) -> None:
    dist.get_command_class("build").sub_commands.append(
        (build_aliases.__name__, None),
    )
    dist.get_command_class("install").sub_commands.append(
        (install_aliases.__name__, None),
    )
