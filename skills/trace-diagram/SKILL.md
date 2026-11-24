---
name: trace-diagram
description: 把已有流程图、判断树或泳道图中的指定业务情景沿原图箭头做成可复核的动画。用于用户给出图片、PDF 页、SVG 或白板导出图，希望演示分支、交接、回路或纠正某条路线时。Use for screenshot-to-animation and scenario walkthroughs on existing diagrams.
---

# 流程图路径动画

用当前对话模型的视觉能力读图；随附的 Python 程序负责准备图像、校验路线和生成文件。全程不需要另外的模型 API 密钥。用本 Skill 所在目录定位 `scripts/trace.py`。

1. 读取用户的图和要演示的情景。运行 `python trace.py prepare INPUT --out sheet.png --grid grid.png`，得到正向、无裁切的原图和带像素坐标的辅助图。PDF 可用 `--page N`。保持同一像素坐标系，查看原图以辨认箭头尖端，查看网格图以量取坐标；必要时放大局部。可用的 SVG、draw.io 等源文件有助于确认连接关系；draw.io 请同时取得对应 PNG/SVG 导出图。
2. 为可见业务节点、每一条有方向的连线分配稳定编号 N1、E1 等，记录起终点、文字条件和沿线折点。不要把线的交叉、图例、分组框或泳道当作新业务节点。无箭头的对应或归属关系不代表时间先后。曲线用足够多的采样点跟随。不能辨认方向或终点时给该边填写具体的 `uncertain`，缺失端点可填 null。
3. 把用户的情景写成有限的连续边序列。条件须和题意及图上标签相符；回退可重复经过同一条边。若用户未选分支且图意清楚，提供两个有名字的演示情景；没有证据选择的路径保留疑点。不要虚构边来满足情景。结构及示例见 [路线格式](references/route.md)。
4. 先制作可编辑 JSON 和编号预览：`python trace.py review sheet.png route.json --scene return --out review.png`。打开预览，检查每条选中边的箭头、折点和端点，并把它和用户情景相对照。存在歧义时，提供预览和需确认的边。若用户纠正一条边，保留其编号和无关边，重新校验受影响的情景。
5. 输出动画：`python trace.py render sheet.png route.json --scene return --out demo.gif`。相同命令支持 .mp4。常见中文系统字体可自动匹配；缺字体时可传 `--font FONT_FILE`。检查实际成片、持续时间和返回分支。交付原图对应的编号预览、路线 JSON 和播放文件。说明哪条路线已核对、哪些局部仍存疑。简洁列出选中的业务步骤。
