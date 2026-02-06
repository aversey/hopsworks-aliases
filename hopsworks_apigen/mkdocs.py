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

from dataclasses import dataclass, field
from textwrap import indent
from typing import TYPE_CHECKING, cast

import griffe
import mkdocs.config.config_options as opt
import yaml
from mkdocs.config import Config
from mkdocs.config.defaults import get_schema
from mkdocs.plugins import BasePlugin, get_plugin_logger
from mkdocs.structure.files import File, Files

from .griffe import HopsworksApigenGriffe


if TYPE_CHECKING:
    from collections.abc import Iterator

    from mkdocs.config.config_options import Plugins
    from mkdocs.config.defaults import MkDocsConfig


PLUGIN_NAME = "hopsworks-apigen"

MOD_SYMBOL = '<code class="doc-symbol doc-symbol-nav doc-symbol-module"></code>'

logger = get_plugin_logger(PLUGIN_NAME)


class PluginConfig(Config):
    """Configuration options for hopsworks-apigen mkdocs plugin."""

    modules = opt.ListOfItems[str](opt.Type(str))
    """List of importable Python modules to scan for @public entities."""
    nav_section_title = opt.Type(str, default="API Reference")
    """Title for the API reference section in the navigation."""
    api_root_uri = opt.Type(str, default="reference")
    """Root folder for API docs in the generated site."""


class HopsworksApigenMkDocs(BasePlugin[PluginConfig]):
    """MkDocs plugin that documents modules containing @public entities."""

    nav: _NavNode
    objects_by_module: dict[str, list[tuple[str, int]]]  # (object_path, order)
    root_modules: set[str]

    def on_config(self, config: MkDocsConfig) -> MkDocsConfig | None:
        """Ensure mkdocstrings is available."""
        if "mkdocstrings" not in config.plugins:
            for name, option in get_schema():
                if name == "plugins":
                    plugins_option = cast("Plugins", option)
                    plugins_option.load_plugin_with_namespace("mkdocstrings", {})
                    logger.warning(
                        "'mkdocstrings' not found in plugins list. "
                        f"Added automatically by {PLUGIN_NAME}."
                    )
                    break

        self.nav = _NavNode(title=self.config.nav_section_title)
        self.objects_by_module = {}
        self.root_modules = set(self.config.modules)
        return None

    def on_files(self, files: Files, /, *, config: MkDocsConfig) -> None:
        """Generate virtual doc files for modules with @public entities."""
        self._collect_public_objects()

        for module_path in sorted(self.objects_by_module):
            # Sort by order descending, then alphabetically
            sorted_objects = sorted(
                self.objects_by_module[module_path],
                key=lambda x: (-x[1], x[0]),
            )
            object_paths = [path for path, _ in sorted_objects]
            docs_path = self._module_doc_path(module_path)
            content = self._module_markdown(module_path, object_paths)

            logger.debug("Documenting module %r at %s", module_path, docs_path)

            file = File.generated(config, src_uri=docs_path, content=content)
            if file.src_uri in files.src_uris:
                files.remove(file)
            files.append(file)

            self.nav.add_module(module_path, docs_path)

        if cfg_nav := config.nav:
            _merge_nav(cfg_nav, self.config.nav_section_title, self.nav.as_list())

    def _collect_public_objects(self) -> None:
        """Load modules with griffe and populate objects_by_module."""
        loader = griffe.GriffeLoader(
            extensions=griffe.Extensions(HopsworksApigenGriffe())
        )

        modules = {}
        for module_name in self.config.modules:
            try:
                modules[module_name] = loader.load(module_name)
            except griffe.AliasResolutionError as e:
                logger.warning("Failed to load module %r: %s", module_name, e)
                continue

        loader.resolve_aliases()

        for module_name in self.config.modules:
            module = modules.get(module_name)

            if not isinstance(module, griffe.Module):
                logger.warning("Loaded object %r is not a module", module_name)
                continue

            for submodule in self._walk_modules(module):
                for member in submodule.members.values():
                    logger.debug("Examining member %r of %r", member, submodule)
                    if isinstance(member, griffe.Alias):
                        continue
                    if isinstance(member, (griffe.Class, griffe.Function)):
                        info = member.extra.get("hopsworks_apigen")
                        if info and info["is_public"]:
                            primary_mod = self._primary_module(member)
                            object_path = f"{member.module.path}.{member.name}"
                            order = info.get("order", 0)
                            if primary_mod not in self.objects_by_module:
                                self.objects_by_module[primary_mod] = []
                            self.objects_by_module[primary_mod].append((object_path, order))

    def _walk_modules(self, module: griffe.Module) -> Iterator[griffe.Module]:
        """Recursively yield all modules."""
        yield module
        for member in module.members.values():
            if isinstance(member, griffe.Alias):
                continue
            if isinstance(member, griffe.Module):
                yield from self._walk_modules(member)

    def _primary_module(self, member: griffe.Class | griffe.Function) -> str:
        """Determine the primary public module for a member.

        The primary module is the module part of the first path in @public(), or the declaring module if no explicit paths are given.
        """
        info = member.extra.get("hopsworks_apigen")
        if info:
            aliases = info["aliases"]
            if aliases:
                target = aliases[0]["target_module"]
                # Empty target means we are publishing in the declaring module
                if target:
                    return target
        return member.module.path

    def _module_doc_path(self, module_path: str) -> str:
        """Compute the docs file path for a module."""
        parts = module_path.split(".")
        docpath = f"{self.config.api_root_uri}/{'/'.join(parts)}"
        if module_path in self.root_modules:
            return f"{docpath}/index.md"
        return f"{docpath}.md"

    def _module_markdown(self, module_path: str, object_paths: list[str]) -> str:
        """Generate markdown content for a module's doc page."""
        options = {"heading_level": 2, "show_root_heading": True}
        options_str = indent(yaml.dump({"options": options}), "    ")

        module_options = {
            "heading_level": 1,
            "show_root_heading": True,
            "members": False,
            "show_root_full_path": True,
        }
        module_options_str = indent(yaml.dump({"options": module_options}), "    ")
        lines = [
            f"---\ntitle: {module_path}\n---\n",
            f"::: {module_path}\n{module_options_str}",
        ]

        for object_path in object_paths:
            lines.append(f"::: {object_path}\n{options_str}")

        return "\n".join(lines)


@dataclass
class _NavNode:
    """Node for building navigation tree."""

    title: str = ""
    doc_path: str | None = None
    children: dict[str, _NavNode] = field(default_factory=dict)

    def add_module(self, module_path: str, docs_path: str) -> None:
        """Add a module to the navigation tree."""
        parts = module_path.split(".")
        node = self
        for part in parts[:-1]:
            if part not in node.children:
                node.children[part] = _NavNode(title=part)
            node = node.children[part]
        name = parts[-1]
        node.children[name] = _NavNode(title=name, doc_path=docs_path)

    def as_list(self) -> list:
        """Convert tree to mkdocs nav list format."""
        result = []
        for name, child in sorted(self.children.items()):
            if child.doc_path and not child.children:
                result.append({f"{MOD_SYMBOL} {name}": child.doc_path})
            elif child.children:
                child_list = child.as_list()
                if child.doc_path:
                    child_list.insert(0, child.doc_path)
                result.append({f"{MOD_SYMBOL} {name}": child_list})
        return result


def _merge_nav(cfg_nav: list, section_title: str, nav_list: list) -> None:
    """Merge our navigation into the existing config nav."""
    for position, item in enumerate(list(cfg_nav)):
        if isinstance(item, str) and item == section_title:
            cfg_nav[position] = {section_title: nav_list}
            return
        if isinstance(item, dict):
            name = next(iter(item.keys()))
            if name == section_title:
                cfg_nav[position] = {section_title: nav_list}
                return
    cfg_nav.append({section_title: nav_list})
