"""hwp-page MCP 서버 — HWPX 쪽(페이지) 방향/크기 변경.

한글 COM 의 PageSetup 은 저장 시 landscape 플래그가 먹지 않는다.
이 서버는 .hwpx(zip) 안의 Contents/section*.xml 의 <hp:pagePr> 를 직접 패치한다.
의존성: 표준 라이브러리 + mcp 만.
"""
import asyncio
import os
import re
import shutil
import zipfile
from collections import Counter

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# HWPUNIT (1mm = 283.465). 세로 기준 (짧은 변 = 폭).
PAPERS = {
    "A4": (59528, 84188),
    "B5": (51591, 72862),
    "A5": (42063, 59528),
    "LETTER": (61199, 79370),
}

HWP_RULES = """한글(hwp/hwpx) 문서를 만들거나 고칠 때 지킬 선생님 규칙:
- 표 안의 구분 짓는 말(첫 열·머리글)과 짧은 말(날짜·장소처럼 한 줄 이내)은 가로·세로 가운데 정렬. 긴 문장 칸만 왼쪽 정렬. 머리글 줄은 굵게.
- 정렬은 표를 다 채운 뒤 마지막에 한다 (표 만들며 바로 하면 COM 커서가 꼬인다).
- 만들거나 고친 뒤에는 PDF 로 내보내 쪽 수·표 넘침을 눈으로 확인한다.
- 글자 크기는 본문 10pt 가 기본. 상황에 맞게 키우거나 줄인다 — 한두 줄 넘쳐 쪽이 늘면 9~9.5pt 로 줄이고,
  쪽에 빈 곳이 많으면 11~12pt 로 키운다. 제목은 본문보다 크게, 표 안 긴 글은 본문보다 조금 작게 해도 된다.
- «1) 가. - ①» 처럼 부호로 시작하는 문단은 둘째 줄을 부호 뒤 글자에 맞춘다 (indent_bullets)."""

server = Server("hwp-page", instructions=HWP_RULES)


MM = 283.465  # 1mm = 283.465 HWPUNIT
MARGIN_KEYS = ["top", "bottom", "left", "right", "header", "footer", "gutter"]
MARGIN_KO = {"top": "위", "bottom": "아래", "left": "왼쪽", "right": "오른쪽",
             "header": "머리말", "footer": "꼬리말", "gutter": "제본"}


def read_margins(path: str) -> dict[str, float]:
    """첫 섹션의 쪽 여백(mm)."""
    with zipfile.ZipFile(path) as z:
        for n in sorted(z.namelist()):
            if re.search(r"Contents/section\d+\.xml$", n):
                m = re.search(r"<hp:margin\b[^>]*/>", z.read(n).decode("utf-8"))
                if m:
                    return {k: round(int(v) / MM, 1)
                            for k, v in re.findall(r'(\w+)="(\d+)"', m.group(0)) if k in MARGIN_KEYS}
    return {}


def body_font_pt(path: str) -> float:
    """본문 글자 크기(pt) = 본문에서 가장 많이 쓴 글자 모양의 크기."""
    refs: Counter = Counter()
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if re.search(r"Contents/section\d+\.xml$", n):
                refs.update(re.findall(r'charPrIDRef="(\d+)"', z.read(n).decode("utf-8")))
        header = z.read("Contents/header.xml").decode("utf-8")
    heights = {}
    for tag in re.findall(r"<hh:charPr\b[^>]*>", header):
        i, h = re.search(r'\bid="(\d+)"', tag), re.search(r'\bheight="(\d+)"', tag)
        if i and h:
            heights[i.group(1)] = int(h.group(1))
    base = next((heights[r] for r, _ in refs.most_common() if r in heights), 1000)
    return base / 100


def patch_hwpx(path: str, orientation: str | None, paper: str,
               margins: dict[str, float] | None = None,
               font_ratio: float | None = None) -> list[str]:
    if orientation:
        land = orientation.lower().startswith("land")
        short, long_ = PAPERS[paper.upper()]
        if land:
            pw, ph, flag = long_, short, "WIDELY"
        else:
            pw, ph, flag = short, long_, "NARROWLY"

    sec_re = re.compile(r"Contents/section\d+\.xml$")
    tag_re = re.compile(r"<hp:pagePr\b[^>]*>")
    margin_re = re.compile(r"<hp:margin\b[^>]*/>")
    changed: list[str] = []
    tmp = path + ".tmp"

    def fix_margin(m: re.Match) -> str:
        tag = m.group(0)
        for k, mm in (margins or {}).items():
            v = round(mm * MM)
            if re.search(rf'\b{k}="\d+"', tag):
                tag = re.sub(rf'\b{k}="\d+"', f'{k}="{v}"', tag, count=1)
            else:
                tag = tag.replace("<hp:margin", f'<hp:margin {k}="{v}"', 1)
        return tag

    def fix_tag(m: re.Match) -> str:
        tag = m.group(0)
        if "landscape=" in tag:
            tag = re.sub(r'landscape="[^"]*"', f'landscape="{flag}"', tag)
        else:
            tag = tag.replace("<hp:pagePr", f'<hp:pagePr landscape="{flag}"', 1)
        if re.search(r'\bwidth="\d+"', tag):
            tag = re.sub(r'\bwidth="\d+"', f'width="{pw}"', tag, count=1)
        if re.search(r'\bheight="\d+"', tag):
            tag = re.sub(r'\bheight="\d+"', f'height="{ph}"', tag, count=1)
        return tag

    def fix_charpr(m: re.Match) -> str:
        return re.sub(r'\bheight="(\d+)"',
                      lambda h: f'height="{max(100, round(int(h.group(1)) * font_ratio))}"',
                      m.group(0), count=1)

    with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(tmp, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if sec_re.search(info.filename):
                text = data.decode("utf-8")
                new = tag_re.sub(fix_tag, text) if orientation else text
                if margins:
                    new = margin_re.sub(fix_margin, new)
                if new != text:
                    changed.append(info.filename)
                data = new.encode("utf-8")
            elif font_ratio and info.filename == "Contents/header.xml":
                text = data.decode("utf-8")
                data = re.sub(r"<hh:charPr\b[^>]*>", fix_charpr, text).encode("utf-8")
                changed.append(info.filename)
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type          # mimetype=STORED 유지
            zi.external_attr = info.external_attr
            zout.writestr(zi, data)

    os.replace(tmp, path)
    return changed


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="set_page",
            description=(
                "HWPX 파일의 쪽 방향/크기와 쪽 여백(mm)을 바꾼다. 한글 COM PageSetup 이 안 먹히는 "
                "landscape 전환용. section*.xml 의 <hp:pagePr>/<hp:margin> 을 직접 수정하고 .bak 백업을 남긴다. "
                "여백만 바꿀 땐 orientation 을 빼고 바꿀 여백만 준다(안 준 여백은 그대로). "
                "font_size 를 주면 본문 글자 크기를 바꾸고 제목 등 다른 크기도 같은 비율로 맞춘다. "
                "file_path 만 주면 지금 여백·본문 글자 크기를 알려 준다. (.hwpx 전용, .hwp 미지원)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "HWPX 파일 절대경로"},
                    "orientation": {
                        "type": "string",
                        "enum": ["landscape", "portrait"],
                        "description": "landscape=가로, portrait=세로. 빼면 방향·용지는 그대로",
                    },
                    "paper": {
                        "type": "string",
                        "enum": list(PAPERS),
                        "default": "A4",
                    },
                    **{k: {"type": "number", "minimum": 0,
                           "description": f"{MARGIN_KO[k]} 여백(mm)"} for k in MARGIN_KEYS},
                    "font_size": {
                        "type": "number", "minimum": 1,
                        "description": (
                            "본문 글자 크기(pt). 제목·작은 글씨도 같은 비율로 함께 커지거나 작아진다. "
                            "기본은 10. 쪽이 한두 줄 넘치면 9~9.5, 빈 곳이 많으면 11~12 처럼 상황에 맞게 고른다"
                        ),
                    },
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="indent_bullets",
            description=(
                "«1) 가. - ① ※ (1)» 같은 부호로 시작하는 문단을 부호 뒤 첫 글자에 맞춰 내어쓰기한다 "
                "(둘째 줄이 부호 아래로 들어가지 않게). 표 칸 안 문단도 포함. 실제 한글 프로그램(COM)으로 "
                "«여기까지 내어쓰기»(Shift+Tab)를 눌러 글꼴과 상관없이 맞는다. .hwp/.hwpx 모두 된다. "
                "한글에서 그 파일을 열어 두었으면 먼저 닫아야 한다. .bak 백업을 남긴다."
            ),
            inputSchema={
                "type": "object",
                "properties": {"file_path": {"type": "string", "description": "HWP/HWPX 파일 절대경로"}},
                "required": ["file_path"],
            },
        ),
    ]


BULLET_RE = re.compile(
    r"^(\s*(?:\d{1,2}[.)]|\(\d{1,2}\)|[가-힣][.)]|\([가-힣]\)|[ㄱ-ㅎ][.)]|[①-⑳]|[-·•※○●□■◦▶▷]))\s+"
)


def indent_bullets(path: str) -> int:
    """부호 문단마다 부호 뒤에 커서를 두고 «여기까지 내어쓰기». 고친 문단 수를 돌려준다."""
    import pythoncom
    import win32com.client as wc

    pythoncom.CoInitialize()
    hwp = wc.DispatchEx("HWPFrame.HwpObject")  # 새 한글 — 선생님이 열어 둔 창에 붙지 않는다
    try:
        hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        hwp.XHwpWindows.Item(0).Visible = False
        if not hwp.Open(path, "", "forceopen:true"):
            raise RuntimeError("한글에서 파일을 못 열었다")
        # 1) 문서를 훑으며 부호로 시작하는 문단의 위치를 모은다
        spots, seen = [], set()
        hwp.InitScan(0x04, 0x0077)  # 0x04 = 표 칸 안까지, 0x77 = 문서 처음~끝
        try:
            for _ in range(200000):  # ponytail: 안전장치, 아주 긴 문서면 늘린다
                state, text = hwp.GetText()
                # 0=더 없음 1=끝 2=글자 3=다음 문단 4/5=표 칸 들어감/나옴 101↑=오류
                if state <= 1 or state >= 100:
                    break
                text = (text or "").lstrip("\r\n")
                if state not in (2, 3, 4) or not text:
                    continue
                hwp.MovePos(201)  # 방금 읽은 조각의 시작으로
                lst, para, pos = hwp.GetPos()  # 문서 첫 문단은 숨은 조판 부호 때문에 pos 가 0 이 아니다
                if (lst, para) in seen:  # 문단의 첫 조각만 본다
                    continue
                seen.add((lst, para))
                m = BULLET_RE.match(text)
                if m:
                    spots.append((lst, para, pos + len(m.group(0))))
        finally:
            hwp.ReleaseScan()
        # 2) 부호+공백 바로 뒤에서 Shift+Tab
        for lst, para, col in spots:
            hwp.SetPos(lst, para, col)
            hwp.Run("ParagraphShapeIndentAtCaret")
        fmt = "HWPX" if path.lower().endswith(".hwpx") else "HWP"
        hwp.SaveAs(path, fmt, "")
        return len(spots)
    finally:
        hwp.Clear(1)
        hwp.Quit()
        pythoncom.CoUninitialize()


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "indent_bullets":
        fp = arguments["file_path"]
        if not os.path.isfile(fp):
            return [types.TextContent(type="text", text=f"파일 없음: {fp}")]
        bak = fp + ".bak"
        shutil.copy2(fp, bak)
        try:
            n = await asyncio.to_thread(indent_bullets, fp)
        except Exception as e:
            shutil.copy2(bak, fp)
            return [types.TextContent(type="text", text=f"실패({e}). 원본 복구함.")]
        return [types.TextContent(type="text", text=f"OK  내어쓰기한 문단 {n}개\n백업: {bak}")]
    if name != "set_page":
        raise ValueError(f"unknown tool: {name}")
    fp = arguments["file_path"]
    orientation = arguments.get("orientation")
    paper = (arguments.get("paper") or "A4").upper()
    margins = {k: float(arguments[k]) for k in MARGIN_KEYS if arguments.get(k) is not None}
    font_size = arguments.get("font_size")

    if not os.path.isfile(fp):
        return [types.TextContent(type="text", text=f"파일 없음: {fp}")]
    if not fp.lower().endswith(".hwpx"):
        return [types.TextContent(type="text", text="HWPX 만 지원한다 (.hwp 는 불가).")]
    if paper not in PAPERS:
        return [types.TextContent(type="text", text=f"지원 용지: {', '.join(PAPERS)}")]

    def fmt(m: dict) -> str:
        return ", ".join(f"{MARGIN_KO[k]} {m[k]:g}" for k in MARGIN_KEYS if k in m) + " (mm)"

    before, pt = read_margins(fp), body_font_pt(fp)
    if not orientation and not margins and not font_size:
        return [types.TextContent(type="text", text=f"지금 여백: {fmt(before)}\n본문 글자: {pt:g}pt")]

    bak = fp + ".bak"
    shutil.copy2(fp, bak)
    try:
        changed = patch_hwpx(fp, orientation, paper, margins,
                             float(font_size) / pt if font_size else None)
    except Exception as e:
        shutil.copy2(bak, fp)
        return [types.TextContent(type="text", text=f"실패({e}). 원본 복구함.")]

    lines = ["OK"]
    if orientation:
        lines.append(f"방향={orientation}, 용지={paper}")
    if margins:
        lines.append(f"여백 전: {fmt(before)}")
        lines.append(f"여백 후: {fmt(read_margins(fp))}")
    if font_size:
        lines.append(f"본문 글자: {pt:g}pt → {body_font_pt(fp):g}pt (다른 크기도 같은 비율)")
    lines.append(f"수정 섹션: {', '.join(changed) if changed else '없음(pagePr 못 찾음)'}")
    lines.append(f"백업: {bak}")
    return [types.TextContent(type="text", text="\n".join(lines))]


async def main() -> None:
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
