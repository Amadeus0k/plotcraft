"""Ruamel round-trip YAML document model.

The document is a ruamel CommentedMap tree, loaded/dumped with the
round-trip loader so existing comments and key order survive edits made
through the GUI. Every mutation funnels through this module (get/set/delete
key, list add/remove/duplicate/reorder) so a future undo stack has a single
choke point to hook into.

Node addressing: a "path" is a tuple of dict keys / list indices, e.g.
("figures", 1, "panels", 2, "series", 0). get_node() walks the tree.
"""

import copy
import os

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

_yaml = YAML(typ="rt")
_yaml.default_flow_style = False
_yaml.preserve_quotes = True
_yaml.width = 100
_yaml.indent(mapping=2, sequence=4, offset=2)


def new_document():
    doc = CommentedMap()
    doc["project"] = "default"
    doc["plots"] = CommentedSeq()
    doc["figures"] = CommentedSeq()
    return doc


def load(path):
    with open(path, "r") as fh:
        doc = _yaml.load(fh)
    if doc is None:
        doc = new_document()
    doc.setdefault("plots", CommentedSeq())
    doc.setdefault("figures", CommentedSeq())
    return doc


def dump(doc, path):
    with open(path, "w") as fh:
        _yaml.dump(doc, fh)


def _has_comments(node, _seen=None):
    if _seen is None:
        _seen = set()
    if id(node) in _seen:
        return False
    _seen.add(id(node))

    ca = getattr(node, "ca", None)
    if ca is not None and (ca.comment or ca.items):
        return True
    if isinstance(node, dict):
        return any(_has_comments(v, _seen) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(_has_comments(v, _seen) for v in node)
    return False


def file_has_comments(path):
    with open(path, "r") as fh:
        text = fh.read()
    return any(line.strip().startswith("#") for line in text.splitlines())


def get_node(doc, node_path):
    node = doc
    for key in node_path:
        node = node[key]
    return node


def get_parent(doc, node_path):
    return get_node(doc, node_path[:-1]), node_path[-1]


def set_key(doc, node_path, key, value):
    node = get_node(doc, node_path)
    node[key] = value


def delete_key(doc, node_path, key):
    node = get_node(doc, node_path)
    if key in node:
        del node[key]


def ensure_dict(doc, node_path, key, defaults=None):
    """Ensure node[key] is a dict (creating it from `defaults` if absent),
    and return its node_path. Used to turn on a nested section (legend,
    zoom, smooth, fontsize) for the first time."""
    node = get_node(doc, node_path)
    if not isinstance(node.get(key), dict):
        node[key] = CommentedMap(defaults or {})
    return node_path + (key,)


def render_copy(doc, node_path):
    """Deep copy of the node at `node_path`, safe to hand to plotter's
    render_plot/render_figure.

    plotter._assign_colors / _assign_colors_panels WRITE auto-assigned
    colors back into the series dicts they're given. Rendering the live
    document directly would bake those colors into the user's YAML on the
    very next save, permanently breaking "same label -> same color" and
    cluttering the file with colors the user never chose. Render a copy,
    always.
    """
    node = get_node(doc, node_path)
    return copy.deepcopy(node)


def add_list_item(doc, list_path, item, index=None):
    lst = get_node(doc, list_path)
    if index is None:
        lst.append(item)
        return len(lst) - 1
    lst.insert(index, item)
    return index


def remove_list_item(doc, list_path, index):
    lst = get_node(doc, list_path)
    del lst[index]


def duplicate_list_item(doc, list_path, index):
    lst = get_node(doc, list_path)
    item = lst[index]
    clone = copy.deepcopy(item) if item is not None else None
    lst.insert(index + 1, clone)
    return index + 1


def move_list_item(doc, list_path, from_index, to_index):
    lst = get_node(doc, list_path)
    item = lst.pop(from_index)
    lst.insert(to_index, item)


class Document:
    """Owns the loaded YAML tree plus its filesystem/dirty-state bookkeeping."""

    def __init__(self, doc=None, path=None, had_comments=False):
        self.doc = doc if doc is not None else new_document()
        self.path = path
        self.dirty = False
        self.had_comments = had_comments
        self.data_dir_override = None

    @classmethod
    def new(cls):
        return cls()

    @classmethod
    def open(cls, path):
        return cls(doc=load(path), path=path, had_comments=file_has_comments(path))

    def save(self, path=None):
        target = path or self.path
        if target is None:
            raise ValueError("No path to save to")
        dump(self.doc, target)
        self.path = target
        self.dirty = False

    @property
    def project_dir(self):
        if self.path is None:
            return os.getcwd()
        return os.path.dirname(os.path.abspath(self.path))

    @property
    def data_dir(self):
        if getattr(self, "data_dir_override", None):
            return self.data_dir_override
        return os.path.join(self.project_dir, "data")

    def get(self, node_path):
        return get_node(self.doc, node_path)

    def set_key(self, node_path, key, value):
        set_key(self.doc, node_path, key, value)
        self.dirty = True

    def delete_key(self, node_path, key):
        delete_key(self.doc, node_path, key)
        self.dirty = True

    def ensure_dict(self, node_path, key, defaults=None):
        result = ensure_dict(self.doc, node_path, key, defaults)
        self.dirty = True
        return result

    def render_copy(self, node_path):
        return render_copy(self.doc, node_path)

    def add_list_item(self, list_path, item, index=None):
        idx = add_list_item(self.doc, list_path, item, index)
        self.dirty = True
        return idx

    def remove_list_item(self, list_path, index):
        remove_list_item(self.doc, list_path, index)
        self.dirty = True

    def duplicate_list_item(self, list_path, index):
        idx = duplicate_list_item(self.doc, list_path, index)
        self.dirty = True
        return idx

    def move_list_item(self, list_path, from_index, to_index):
        move_list_item(self.doc, list_path, from_index, to_index)
        self.dirty = True
