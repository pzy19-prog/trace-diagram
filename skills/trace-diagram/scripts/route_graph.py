"""Validate pixel geometry and directed scenario walks, independently of rendering."""
import json
import math
import re
from pathlib import Path


def require(ok, explanation):
    if not ok:
        raise ValueError(explanation)


def index(items, pattern, kind):
    require(isinstance(items, list), f"{kind}: expected an array")
    result = {}
    for item in items:
        require(isinstance(item, dict), f"{kind}: expected an object")
        key = item.get("id")
        require(isinstance(key, str) and re.fullmatch(pattern, key), f"{kind}: invalid id {key!r}")
        require(key not in result, f"{kind}: duplicate {key}")
        result[key] = item
    return result


def inside(box, point, slack):
    x, y = point
    left, top, right, bottom = box
    return left-slack <= x <= right+slack and top-slack <= y <= bottom+slack


class Graph:
    def __init__(self, data, size):
        require(isinstance(data, dict) and data.get("version") == 1, "expected route version 1")
        require(data.get("size") == list(size), "route size differs from the input image")
        self.size = size
        self.nodes = index(data.get("nodes"), r"N[1-9][0-9]*", "nodes")
        self.edges = index(data.get("edges"), r"E[1-9][0-9]*", "edges")
        self.scenes = index(data.get("scenes"), r"[\w.-]+", "scenes")
        require(self.nodes, "no nodes")
        self.check_geometry()
        for sid, scene in self.scenes.items():
            require(isinstance(scene.get("label"), str) and scene["label"].strip(), f"{sid}: missing label")
            require(isinstance(scene.get("start"), str) and scene["start"] in self.nodes, f"{sid}: invalid start")
            require(isinstance(scene.get("edges"), list) and scene["edges"], f"{sid}: empty walk")
            for edge in scene["edges"]:
                require(isinstance(edge, str) and edge in self.edges, f"{sid}: unknown edge {edge}")

    @classmethod
    def read(cls, path, size):
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, f"duplicate JSON key: {key}")
                result[key] = value
            return result
        return cls(json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique_pairs), size)

    def point_ok(self, pt):
        return (isinstance(pt, list) and len(pt) == 2
                and all(type(v) in (int, float) and 0 <= v < lim for v, lim in zip(pt, self.size)))

    def check_geometry(self):
        for key, node in self.nodes.items():
            box = node.get("box")
            require(isinstance(node.get("label"), str) and node["label"].strip(), f"{key}: missing label")
            require(isinstance(box, list) and len(box) == 4 and self.point_ok(box[:2])
                    and self.point_ok(box[2:]) and box[0] < box[2] and box[1] < box[3], f"{key}: invalid box")
        slack = max(4, math.hypot(*self.size)*.012)
        for key, edge in self.edges.items():
            for name in ("condition", "uncertain"):
                require(isinstance(edge.get(name, ""), str), f"{key}: {name} must be text")
            pts = edge.get("points")
            require(isinstance(pts, list) and len(pts) >= 2 and all(self.point_ok(p) for p in pts),
                    f"{key}: invalid points")
            require(all(a != b for a,b in zip(pts, pts[1:])), f"{key}: consecutive identical points")
            for attr, pos in (("from", 0), ("to", -1)):
                node_id = edge.get(attr)
                if node_id is None and edge.get("uncertain", "").strip():
                    continue
                require(isinstance(node_id, str) and node_id in self.nodes, f"{key}: invalid {attr} node")
                require(inside(self.nodes[node_id]["box"], pts[pos], slack),
                        f"{key}: {attr} end of the drawn line misses {node_id}")

    def scene(self, sid):
        require(sid in self.scenes, f"unknown scene {sid!r}. Available: {', '.join(self.scenes)}")
        return self.scenes[sid]

    def walk(self, sid):
        scene = self.scene(sid)
        node = scene["start"]
        edges = []
        for key in scene["edges"]:
            edge = self.edges[key]
            require(not edge.get("uncertain", "").strip(), f"{key}: {edge.get('uncertain')}")
            require(edge["from"] == node, f"{sid}: {key} starts at {edge['from']}, expected {node}")
            node = edge["to"]
            edges.append(edge)
        return edges
