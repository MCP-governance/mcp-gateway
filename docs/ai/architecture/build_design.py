"""build_architecture.py 배치를 Claude Design 캔버스 아트보드(.dc.html)로 옮긴다.

python -X utf8 build_design.py <assets.json> <출력 root>   → <root>/project/canvas.json, *.dc.html
assets.json: 아이콘 키 → 캔버스 자산 id (/_blob/<id>)
"""
import html, json, math, sys
from datetime import datetime, timezone
from pathlib import Path

import build_architecture as b

OFF = 54  # 요소를 루트 가장자리에서 64px 안쪽에 둔다(배치 최소 좌표 10)
FILES = [("Main.dc.html", "1 전체 아키텍처", b.page1), ("Network.dc.html", "2 망·배치", b.page2),
         ("EndpointKit.dc.html", "3 엔드포인트 키트", b.page3)]


def esc(s):
    return html.escape(str(s), quote=True)


class DC:
    def __init__(self, page, assets):
        self.p, self.assets, self.out, self.mk = page, assets, [], 0

    def px(self, v):
        return int(round(v + OFF))

    def text(self, s, x, y, w, size=11, color=b.TEXT, bold=True, align="left", h=None):
        hh = h or size + 5
        self.out.append(f'<div style="position: absolute; left: {self.px(x)}px; top: {self.px(y)}px; width: {int(w)}px; '
                        f'height: {hh}px; font-size: {size}px; line-height: {hh}px; font-weight: {700 if bold else 400}; '
                        f'color: {color}; text-align: {align}; white-space: nowrap">{esc(s)}</div>')

    def seg(self, x1, y1, x2, y2, color, width, dash, head):
        """직선 구간 하나를 화살표 svg 하나로 (draw 규칙: 수평·수직은 8px 띠, 사선은 상자)"""
        st = (f"position: absolute; left: {{l}}px; top: {{t}}px; width: {{w}}px; height: {{h}}px; overflow: visible; "
              f"fill: none; stroke: {color}; stroke-width: {width}; stroke-linecap: round; stroke-linejoin: round"
              + (f"; stroke-dasharray: {dash}" if dash else ""))
        defs, mend = "", ""
        if head:
            self.mk += 1
            mid = f"dc-arrow-head-filled-{self.mk}"
            defs = (f'<defs><marker id="{mid}" orient="auto" markerWidth="5" markerHeight="5" refX="2" refY="2" '
                    f'overflow="visible"><path d="M0 0 L4 2 L0 4 Z" fill="{color}" stroke="none" '
                    f'style="stroke: none; fill: {color}; fill: context-stroke"></path></marker></defs>')
            mend = f' marker-end="url(#{mid})"'
        h_ = 2 * width if head else 0
        X1, Y1, X2, Y2 = (self.px(v) for v in (x1, y1, x2, y2))
        if Y1 == Y2:  # 수평
            n = abs(X2 - X1) or 1
            left = min(X1, X2)
            d = f"M 0 4 L {n - h_:.1f} 4" if X2 >= X1 else f"M {n} 4 L {h_:.1f} 4"
            box = st.format(l=left, t=Y1 - 4, w=n, h=8)
            self.out.append(f'<svg width="{n}" height="8" viewBox="0 0 {n} 8" preserveAspectRatio="none" '
                            f'style="{box}">{defs}<path d="{d}"{mend}></path></svg>')
        elif X1 == X2:  # 수직
            n = abs(Y2 - Y1) or 1
            top = min(Y1, Y2)
            d = f"M 4 0 L 4 {n - h_:.1f}" if Y2 >= Y1 else f"M 4 {n} L 4 {h_:.1f}"
            box = st.format(l=X1 - 4, t=top, w=8, h=n)
            self.out.append(f'<svg width="8" height="{n}" viewBox="0 0 8 {n}" preserveAspectRatio="none" '
                            f'style="{box}">{defs}<path d="{d}"{mend}></path></svg>')
        else:  # 사선(바퀴살)
            l, t = min(X1, X2), min(Y1, Y2)
            w, h = max(abs(X2 - X1), 1), max(abs(Y2 - Y1), 1)
            dx, dy = X2 - X1, Y2 - Y1
            L = math.hypot(dx, dy)
            ex, ey = X2 - dx / L * h_, Y2 - dy / L * h_
            d = f"M {X1 - l} {Y1 - t} L {ex - l:.1f} {ey - t:.1f}"
            box = st.format(l=l, t=t, w=w, h=h)
            self.out.append(f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
                            f'style="{box}">{defs}<path d="{d}"{mend}></path></svg>')

    def build(self):
        p = self.p
        # 1) 배경 띠·상자
        for bx in p.boxes:
            if bx["kind"] == "legend":
                self.out.append(f'<div style="position: absolute; left: {self.px(bx["x"])}px; top: {self.px(bx["y"])}px; '
                                f'width: {bx["w"]}px; height: {bx["h"]}px; box-sizing: border-box; background: #FFFFFF; '
                                f'border: 1.5px solid {b.COLUMN_BLUE}; border-radius: 4px"></div>')
                continue
            if bx["kind"] == "col":
                style = f"border: 2px solid {b.COLUMN_BLUE}"
            else:
                fill = {"grp": "#F4F8FD", "sub": "#FFFFFF", "lab": "#FBFBFC"}[bx["kind"]]
                stroke = {"grp": "#9DB8DE", "sub": "#C5D3E6", "lab": "#A7B0BC"}[bx["kind"]]
                style = f"background: {fill}; border: 1px {'dashed' if bx['kind'] == 'lab' else 'solid'} {stroke}; border-radius: 4px"
            self.out.append(f'<div style="position: absolute; left: {self.px(bx["x"])}px; top: {self.px(bx["y"])}px; '
                            f'width: {bx["w"]}px; height: {bx["h"]}px; box-sizing: border-box; {style}"></div>')
        # 2) 화살표
        for ed in p.edges:
            color, dash, w = b.EDGE[ed["kind"]]
            pts = b.route(p, ed)
            for i, ((x1, y1), (x2, y2)) in enumerate(zip(pts, pts[1:])):
                last = i == len(pts) - 2
                self.seg(round(x1), round(y1), round(x2), round(y2), color, w, dash, last and ed["kind"] != "blk")
            if ed["kind"] == "blk":
                ex, ey = (self.px(v) for v in pts[-1])
                self.out.append(f'<svg width="14" height="14" viewBox="0 0 14 14" style="position: absolute; left: {ex - 7}px; '
                                f'top: {ey - 7}px; width: 14px; height: 14px; overflow: visible; fill: none; stroke: {color}; '
                                f'stroke-width: 2.4; stroke-linecap: round"><path d="M 1 1 L 13 13 M 13 1 L 1 13"></path></svg>')
        # 3) 노드 카드: 아이콘(원형 테두리) + 이름
        for nd in p.nodes.values():
            color, dash, planned = b.node_ring(nd)
            s = nd["size"]
            lw = max(s, int(len(nd["label"]) * 11.5) + 12)
            ring = "dashed" if ("6 4" in dash or "5 4" in dash) else ("dotted" if dash else "solid")
            img = (f'<img src="/_blob/{self.assets[nd["icon"]]}" alt="" style="width: {s}px; height: {s}px; '
                   f'box-sizing: border-box; border-radius: 50%; border: 3px {ring} {color}; background: #FFFFFF; '
                   f'padding: {s * 0.18:.0f}px; object-fit: contain; flex: none{"; opacity: 0.8" if planned else ""}">'
                   if nd["icon"] in self.assets else
                   f'<img alt="" style="width: {s}px; height: {s}px; border-radius: 50%; border: 3px solid {color}; flex: none">')
            span = f'<span style="font-size: 11px; line-height: 14px; font-weight: 700; color: {b.TEXT}; white-space: nowrap">{esc(nd["label"])}</span>'
            lp = nd["lp"]
            if lp in ("b", "t"):
                left, top = nd["x"] - lw / 2, nd["y"] - s / 2 - (18 if lp == "t" else 0)
                flex = "column" if lp == "b" else "column-reverse"
                ww, hh = lw, s + 18
            else:
                ww, hh = s + lw + 4, s
                left = nd["x"] - s / 2 if lp == "r" else nd["x"] - s / 2 - lw - 4
                top = nd["y"] - s / 2
                flex = "row" if lp == "r" else "row-reverse"
            self.out.append(f'<div style="position: absolute; left: {self.px(left)}px; top: {self.px(top)}px; width: {int(ww)}px; '
                            f'height: {int(hh)}px; box-sizing: border-box; display: flex; flex-direction: {flex}; '
                            f'align-items: center; justify-content: flex-start; gap: 4px">{img}{span}</div>')
        # 4) 글자: 기둥·상자 제목, 연결 라벨, 범례
        for bx in p.boxes:
            if bx["kind"] == "col":
                self.text(bx["label"], bx["x"], bx["y"] + 12, bx["w"], 15, b.COLUMN_BLUE, align="center")
            elif bx["kind"] != "legend" and bx["label"]:
                self.text(bx["label"], bx["x"] + 10, bx["y"] + 5, bx["w"] - 20, 12,
                          align="right" if bx["la"] == "r" else "left")
        for ed in p.edges:
            if not ed["label"]:
                continue
            color = b.EDGE[ed["kind"]][0]
            pts = b.route(p, ed)
            segs = list(zip(pts, pts[1:]))
            k = ed["lab_at"] if ed["lab_at"] is not None else max(range(len(segs)), key=lambda q: math.dist(*segs[q]))
            (x1, y1), (x2, y2) = segs[min(k, len(segs) - 1)]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            tw = 8 * len(ed["label"]) + 10
            self.out.append(f'<div style="position: absolute; left: {self.px(mx - tw / 2)}px; top: {self.px(my - 8)}px; '
                            f'width: {tw}px; height: 16px; font-size: 10px; line-height: 16px; font-weight: 700; '
                            f'color: {color}; background: #FFFFFF; text-align: center">{esc(ed["label"])}</div>')
        lb = next((x for x in p.boxes if x["kind"] == "legend"), None)
        if lb:
            for kind, s, x, y in b.legend_layout(p, lb):
                if kind == "title":
                    self.text(s, x, y - 10, 150, 15, b.COLUMN_BLUE)
                elif kind == "sub":
                    self.text(s, x, y - 8, 260, 11, "#66727F", bold=False)
                elif kind == "cat":
                    self.out.append(f'<div style="position: absolute; left: {self.px(x + 2)}px; top: {self.px(y - 5)}px; '
                                    f'width: 10px; height: 10px; border-radius: 50%; background: {b.CAT[s]}"></div>')
                    self.text(s, x + 18, y - 8, 100, 11, bold=False)
                elif kind == "edge":
                    color, dash, w = b.EDGE[s]
                    self.seg(x, y, x + 24, y, color, w, dash, False)
                    self.text(b.EDGE_NAME[s], x + 30, y - 8, 140, 11, bold=False)
                elif kind == "ring":
                    for i, (lab, rs) in enumerate((("사용 중", "solid"), ("시험·연동", "dotted"), ("개발 예정·재검토", "dashed"))):
                        xx = x + i * 125
                        self.out.append(f'<div style="position: absolute; left: {self.px(xx)}px; top: {self.px(y - 7)}px; '
                                        f'width: 14px; height: 14px; box-sizing: border-box; border-radius: 50%; '
                                        f'border: 2px {rs} #66727F"></div>')
                        self.text(lab, xx + 18, y - 8, 110, 11, bold=False)
            cr = b.credits()
            if cr:
                self.text(cr, lb["x"] + lb["w"] - 418, lb["y"] + lb["h"] - 13, 410, 7, "#B8BFC8", bold=False, align="right", h=10)
        return self.out


def page_html(page, title, assets):
    W, H = page.w + 2 * OFF, page.h + 2 * OFF
    body = "\n".join(DC(page, assets).build())
    props = json.dumps({"$preview": {"width": W, "height": H}})
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&amp;display=swap" rel="stylesheet">
<style>
body{{margin:0}}
a{{color:#265A99}}a:hover{{color:#003878}}
</style>
</helmet>
<div style="position: relative; width: {W}px; height: {H}px; background: #FFFFFF; font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif">
{body}
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{props}'>
class Component extends DCLogic {{
renderVals() {{
return {{}};
}}
}}
</script>
</body>
</html>
""", W, H


def main():
    assets = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    root = Path(sys.argv[2]) / "project"
    root.mkdir(parents=True, exist_ok=True)
    boards, order, x = {}, [], 0
    for name, title, fn in FILES:
        src, W, H = page_html(fn(), title, assets)
        (root / name).write_text(src, encoding="utf-8")
        boards[name] = {"x": x, "y": 0, "w": W, "h": H, "title": title}
        order.append(name)
        x += W + 80
    canvas = {"v": 3, "createdOnFiles": {"v": 1, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
              "title": "MINT 아키텍처", "launch": {"view": "canvas"}, "pages": [], "boards": boards, "order": order,
              "notes": {}, "designSystems": []}
    (root / "canvas.json").write_text(json.dumps(canvas, ensure_ascii=False, indent=1), encoding="utf-8")
    print({n: f"{(root / n).stat().st_size // 1024}KB" for n in order})


if __name__ == "__main__":
    main()
