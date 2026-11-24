#!/usr/bin/env python3
"""Render a visually interpreted flowchart route on its original page. Python 3.10+."""
import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from route_graph import Graph, require

TEAL = "#00786d"
AMBER = "#b64a0c"
MUTED = "#697779"
INK = "#152d32"
PAPER = "#f6f8f5"


def external(name):
    path = shutil.which(name)
    require(path, f"{name} is required for this file format")
    return path


@contextmanager
def output_file(target):
    target.parent.mkdir(exist_ok=True, parents=True)
    fd, name = tempfile.mkstemp(dir=target.parent, suffix=target.suffix)
    os.close(fd)
    temp = Path(name)
    try:
        yield temp
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def read_image(path):
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGBA")
        white = Image.new("RGB", image.size, "white")
        white.paste(image, mask=image.getchannel("A"))
        return white


def prepare(args):
    src = args.input.resolve()
    require(args.page >= 1, "--page starts at 1")
    ext = src.suffix.lower()
    require(args.page == 1 or ext == ".pdf", "--page applies to PDF")
    with tempfile.TemporaryDirectory() as directory:
        pic = Path(directory) / "page.png"
        if ext == ".pdf":
            subprocess.run([external("pdftoppm"), "-f", str(args.page), "-l", str(args.page), "-singlefile",
                            "-scale-to", "2000", "-png", str(src), str(pic.with_suffix(""))], check=True)
        elif ext == ".svg":
            subprocess.run([external("inkscape"), str(src), "--export-type=png", f"--export-filename={pic}"],
                           check=True)
        else:
            pic = src
        im = read_image(pic)
    require(args.out.suffix.lower() == ".png", "--out must be a PNG for prepare")
    dests = [args.out] + ([args.grid] if args.grid else [])
    require(len({src, *(p.resolve() for p in dests)}) == len(dests)+1, "use separate input and output files")
    if args.grid:
        require(args.grid.suffix.lower() == ".png", "--grid must be a PNG")
    with output_file(args.out) as out:
        im.save(out, "PNG")
    if args.grid:
        grid = im.copy()
        d = ImageDraw.Draw(grid, "RGBA")
        spacing = max(25, int(max(im.size) / 12 / 25) * 25)
        f = ImageFont.load_default(size=max(11, spacing // 5))
        for x in range(0, im.width, spacing):
            d.line((x,0,x,im.height), fill=(0,99,155,90))
            d.text((x+2,2), str(x), font=f, fill="#003d60", stroke_width=1, stroke_fill="white")
        for y in range(spacing, im.height, spacing):
            d.line((0,y,im.width,y), fill=(0,99,155,90))
            d.text((2,y+1), str(y), font=f, fill="#003d60", stroke_width=1, stroke_fill="white")
        with output_file(args.grid) as out:
            grid.save(out, "PNG")
    print(f"{args.out}: {im.width} x {im.height}")


def font(size, override):
    if override:
        return ImageFont.truetype(override, size)
    for name in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                 "/System/Library/Fonts/PingFang.ttc", "msyh.ttc", "NotoSansCJKsc-Regular.otf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def fit(d, text, f, width):
    if d.textlength(text, font=f) <= width:
        return text
    while text and d.textlength(text+"…", font=f) > width:
        text = text[:-1]
    return text+"…"


def prefix(points, progress):
    """Follow arclength, including every bend up to the current tip."""
    lengths = [math.dist(a,b) for a,b in zip(points, points[1:])]
    remaining = max(0, min(progress, 1)) * sum(lengths)
    path = [points[0]]
    for (a,b), distance in zip(zip(points, points[1:]), lengths):
        if remaining < distance:
            t = remaining/distance
            path.append((a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])))
            return path
        path.append(b)
        remaining -= distance
    return path


def corners(draw, box, color, line=3):
    x,y,X,Y = box
    arm = min(16, (X-x)/4, (Y-y)/4)
    for cx,cy,dx,dy in ((x,y,1,1),(X,y,-1,1),(x,Y,1,-1),(X,Y,-1,-1)):
        draw.line([(cx+arm*dx,cy),(cx,cy),(cx,cy+arm*dy)], fill=color, width=line)


def badge(d, xy, label, color, f, size):
    x,y = xy
    w = d.textlength(label,font=f) + 10
    h = f.size + 6
    x = max(0,min(size[0]-w-1,x)); y = max(0,min(size[1]-h-1,y))
    d.rounded_rectangle((x,y,x+w,y+h),radius=4,fill=color)
    d.text((x+w/2,y+h/2),label,font=f,fill="white",anchor="mm")


class Overlay:
    def __init__(self, image, graph, override):
        self.image = image.copy()
        self.image.thumbnail((1120,1120),Image.Resampling.LANCZOS)
        self.space = [a/b for a,b in zip(self.image.size,graph.size)]
        self.nodes = graph.nodes
        self.f = font(18, override)
        self.small = font(14, override)

    def pt(self, point):
        return tuple(v*s for v,s in zip(point,self.space))

    def box(self, node_id):
        box = self.nodes[node_id]["box"]
        return (*self.pt(box[:2]), *self.pt(box[2:]))

    def graph_review(self, graph, sid):
        image = self.image.copy()
        d = ImageDraw.Draw(image)
        chosen = set(graph.scene(sid)["edges"]) if sid else set(graph.edges)
        for key, edge in sorted(graph.edges.items(), key=lambda pair: pair[0] in chosen):
            points = [self.pt(p) for p in edge["points"]]
            color = AMBER if edge.get("uncertain","").strip() else (TEAL if key in chosen else MUTED)
            d.line(points, fill=color, width=3)
            if not edge.get("uncertain","").strip():
                a,b = points[-2:]
                angle = math.atan2(b[1]-a[1],b[0]-a[0])
                d.polygon([b]+[(b[0]-11*math.cos(angle+t),b[1]-11*math.sin(angle+t))
                               for t in [-.45,.45]],fill=color)
            x,y = prefix(points,.46)[-1]
            badge(d,(x+4,y+4),key+("?" if edge.get("uncertain","").strip() else ""),color,self.small,image.size)
        for key in self.nodes:
            box = self.box(key)
            corners(d, box, INK, 2)
            badge(d,(box[0],box[1]-22),key,INK,self.small,image.size)
        if not sid:
            return image
        # Repeat traversed edges in the footer so a loop is legible in a still.
        tokens = graph.scene(sid)["edges"]
        lines = []
        line = ""
        for token in tokens:
            candidate = f"{line}  ›  {token}" if line else token
            if line and d.textlength(candidate,font=self.f) > image.width-30:
                lines.append(line)
                line = token
            else:
                line = candidate
        lines.append(line)
        summary = Image.new("RGB",(image.width,image.height+34+26*len(lines)),PAPER)
        summary.paste(image)
        d = ImageDraw.Draw(summary)
        d.text((14,image.height+15),fit(d,graph.scene(sid)["label"],self.small,image.width-28),
               font=self.small,fill=MUTED,anchor="lm")
        for i, row in enumerate(lines):
            d.text((14,image.height+41+26*i),row,font=self.f,fill=INK,anchor="lm")
        return summary

    def frame(self, edges, scene, phase, progress):
        end = phase == len(edges)
        edge = edges[-1] if end else edges[phase]
        source = self.nodes[edge["from"]]["label"]
        target = self.nodes[edge["to"]]["label"]
        hold = progress < .32
        node = edge["to"] if end else edge["from"]
        w,h = self.image.size
        frame = Image.new("RGB",(w,h+70),PAPER)
        frame.paste(self.image)
        d = ImageDraw.Draw(frame)
        if end or hold:
            corners(d,self.box(node),TEAL,4)
        else:
            points = [self.pt(p) for p in edge["points"]]
            line = prefix(points,(progress-.32)/.68)
            d.line(line, fill=TEAL,width=4)
            x,y=line[-1]
            d.ellipse((x-6,y-6,x+6,y+6),fill=TEAL,outline="white",width=2)
        d.line((0,h,w,h),fill="#c6d5d0",width=1)
        num = min(phase+1,len(edges))
        d.text((15,h+17),fit(d,scene["label"],self.small,w-105),fill=MUTED,font=self.small,anchor="lm")
        d.text((w-14,h+17),f"{num:02d} / {len(edges):02d}",fill=MUTED,font=self.small,anchor="rm")
        detail = target if end else f"{source}  →  {target}"
        if not end and edge.get("condition"):
            detail += "  ·  " + edge["condition"]
        d.text((15,h+46),fit(d,detail,self.f,w-30),fill=INK,font=self.f,anchor="lm")
        return frame


def frames(painter, edges, scene):
    for i in range(len(edges)):
        for k in range(20):
            yield painter.frame(edges,scene,i,k/19)
    final = painter.frame(edges,scene,len(edges),1)
    for _ in range(15):
        yield final


def save_animation(path, images, size):
    # Share one palette across GIF frames. Keep only one indexed image per
    # frame inside Pillow's writer and keep RGB frame generation lazy.
    first = next(images)
    if path.suffix.lower() == ".gif":
        seed = first.copy()
        d = ImageDraw.Draw(seed)
        d.rectangle((0,0,12,12),fill=TEAL)
        pal = seed.quantize(colors=254)
        def indexed(im): return im.quantize(palette=pal, dither=Image.Dither.NONE)
        indexed(first).save(path,format="GIF",save_all=True,append_images=(indexed(f) for f in images),
                            duration=80,loop=0,optimize=False,disposal=1)
    else:
        args = [external("ffmpeg"),"-hide_banner","-loglevel","error","-y","-f","rawvideo","-pix_fmt","rgb24",
                "-s",f"{size[0]}x{size[1]}","-framerate","25/2","-i","pipe:0","-an","-vf",
                "pad=ceil(iw/2)*2:ceil(ih/2)*2","-c:v","libx264","-pix_fmt","yuv420p","-movflags","+faststart",str(path)]
        with subprocess.Popen(args,stdin=subprocess.PIPE) as proc:
            try:
                proc.stdin.write(first.tobytes())
                for frame in images:
                    proc.stdin.write(frame.tobytes())
            finally:
                proc.stdin.close()
            if proc.wait():
                raise ValueError("FFmpeg could not encode the MP4")


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    subs = arg.add_subparsers(dest="cmd",required=True)
    prep = subs.add_parser("prepare")
    prep.add_argument("input",type=Path)
    prep.add_argument("--out",required=True,type=Path)
    prep.add_argument("--grid",type=Path)
    prep.add_argument("--page",type=int,default=1)
    for cmd in ("review","render"):
        sub = subs.add_parser(cmd)
        sub.add_argument("input",type=Path)
        sub.add_argument("route",type=Path)
        sub.add_argument("--scene",required=cmd=="render")
        sub.add_argument("--out",required=True,type=Path)
        sub.add_argument("--font")
    opts = arg.parse_args()
    if opts.cmd == "prepare":
        prepare(opts)
        return
    require(opts.out.resolve() not in (opts.input.resolve(),opts.route.resolve()),"output would overwrite an input")
    im = read_image(opts.input)
    graph = Graph.read(opts.route,im.size)
    painter = Overlay(im,graph,opts.font)
    if opts.cmd == "review":
        require(opts.out.suffix.lower()==".png","review output must be PNG")
        image = painter.graph_review(graph,opts.scene)
        with output_file(opts.out) as temp:
            image.save(temp,"PNG")
    else:
        require(opts.out.suffix.lower() in (".mp4",".gif"),"render output must be GIF or MP4")
        edges = graph.walk(opts.scene)
        with output_file(opts.out) as temp:
            save_animation(temp,frames(painter,edges,graph.scene(opts.scene)),(painter.image.width,painter.image.height+70))
    print(opts.out)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"trace-diagram: {exc}")
