from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from pathlib import Path
from app.services import 目录, 装载, 关窗, 贯验, 夹具, 统计, 说明
from app.modules import 观测点换绑 as 换绑模


async def api_概览(request: Request):
    return JSONResponse(目录.概览())


async def api_仓情(request: Request):
    return JSONResponse(说明.仓情())


async def api_窗规_get(request: Request):
    return JSONResponse(目录.窗规())


async def api_窗规_post(request: Request):
    body = await request.json()
    return JSONResponse(目录.改窗规(body))


async def api_网点(request: Request):
    return JSONResponse(目录.网点列表())


async def api_观测(request: Request):
    return JSONResponse(目录.观测列表())


async def api_缓冲(request: Request):
    return JSONResponse(目录.缓冲列表())


async def api_切片(request: Request):
    return JSONResponse(目录.切片列表())


async def api_迟到(request: Request):
    return JSONResponse(目录.迟到列表())


async def api_贯验列表(request: Request):
    return JSONResponse(目录.贯验列表())


async def api_夹具(request: Request):
    return JSONResponse(夹具.列表())


async def api_装载(request: Request):
    body = await request.json()
    return JSONResponse(装载.装一批(body))


async def api_夹具装载(request: Request):
    名 = request.path_params["name"]
    try:
        return JSONResponse(装载.装一批(夹具.读取(名)))
    except FileNotFoundError:
        return JSONResponse({"错误": 名}, status_code=404)


async def api_关窗(request: Request):
    return JSONResponse(关窗.关当前窗())


async def api_贯验(request: Request):
    return JSONResponse(贯验.跑一次())


async def api_统计观测(request: Request):
    return JSONResponse(统计.观测命运())


async def api_统计缓冲(request: Request):
    return JSONResponse(统计.缓冲命运())


async def api_空桩(request: Request):
    root = Path(__file__).resolve().parents[1] / "modules"
    out = []
    if root.is_dir():
        for p in sorted(root.iterdir()):
            if p.is_dir() and p.name != "__pycache__" and (p / "__init__.py").is_file():
                out.append(p.name)
    return JSONResponse({"空桩": out, "条数": len(out)})


def _取新旧(request: Request, body: dict | None = None):
    body = body or {}
    q = request.query_params
    旧 = (
        body.get("旧键") or body.get("旧") or body.get("old_key")
        or body.get("oldKey") or body.get("from")
        or q.get("旧键") or q.get("old_key") or q.get("oldKey")
    )
    新 = (
        body.get("新键") or body.get("新") or body.get("new_key")
        or body.get("newKey") or body.get("to")
        or q.get("新键") or q.get("new_key") or q.get("newKey")
    )
    形 = (
        body.get("形态") or body.get("策略") or body.get("选定形态")
        or body.get("mode") or body.get("strategy")
        or q.get("形态") or q.get("策略") or q.get("选定形态")
        or q.get("mode") or q.get("strategy")
    )
    return 旧, 新, 形


async def api_换绑只读(request: Request):
    """只读接口：默认返回带四字段（旧键/新键/拒因或归档键/valid）的对象。

    - 带 旧键/新键 查询 → 单条规范记录；
    - 不带键 → 信封视图（顶层最近一条字段 + 记录列表）；
    - 显式 列表=1 / 格式=list → bare list。
    """
    q = request.query_params
    if q.get("列表") in ("1", "true", "True") or q.get("格式") == "list" or q.get("all") in ("1", "true"):
        return await api_换绑记录(request)
    旧, 新, _ = _取新旧(request)
    if 旧 is not None or 新 is not None:
        return JSONResponse(换绑模.只读接口(旧键=旧, 新键=新))
    return JSONResponse(换绑模.只读视图())


async def api_换绑入口(request: Request):
    """GET=换绑只读接口；POST=执行换绑（同一资源，方法分派）。"""
    if request.method == "GET":
        旧, 新, _ = _取新旧(request)
        if 旧 is not None or 新 is not None:
            return JSONResponse(换绑模.只读接口(旧键=旧, 新键=新))
        return JSONResponse(换绑模.只读视图())

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    旧, 新, 形 = _取新旧(request, body)
    try:
        rec = 换绑模.换绑(旧, 新, 形态=形)
    except (ValueError, TypeError) as e:
        # 与本仓装载接口同风格：HTTP 200 + valid=false 契约结论（不执行换绑）。
        结论 = 换绑模.校验换绑(旧, 新, 形)
        结论["拒因或归档键"] = 结论.get("拒因或归档键") or str(e)
        结论["valid"] = False
        结论["有效"] = False
        return JSONResponse(结论)
    return JSONResponse(rec)


async def api_换绑记录(request: Request):
    旧 = request.query_params.get("旧键")
    新 = request.query_params.get("新键")
    return JSONResponse(换绑模.记录列表(旧键=旧, 新键=新))


async def api_换绑归档(request: Request):
    return JSONResponse({
        "归档轨": 换绑模.归档列表(),
        "拒载账": 换绑模.拒载列表(),
        "键集合": 换绑模.键集合(),
    })


路由表 = [
    Route("/api/概览", api_概览),
    Route("/api/仓情", api_仓情),
    Route("/api/窗规", api_窗规_get, methods=["GET"]),
    Route("/api/窗规", api_窗规_post, methods=["POST"]),
    Route("/api/网点源", api_网点),
    Route("/api/观测点", api_观测),
    Route("/api/入窗缓冲", api_缓冲),
    Route("/api/窗切片账", api_切片),
    Route("/api/迟到匣", api_迟到),
    Route("/api/窗贯验", api_贯验列表),
    Route("/api/夹具", api_夹具),
    Route("/api/观测点/装载", api_装载, methods=["POST"]),
    Route("/api/观测点/夹具/{name}", api_夹具装载, methods=["POST"]),
    Route("/api/关窗/跑", api_关窗, methods=["POST"]),
    Route("/api/窗贯验/跑", api_贯验, methods=["POST"]),
    Route("/api/统计/观测命运", api_统计观测),
    Route("/api/统计/缓冲命运", api_统计缓冲),
    # 观测点换绑：只读接口 + 执行入口（多路径别名，兼容不同命名习惯）
    Route("/api/观测点换绑", api_换绑入口, methods=["GET", "POST"]),
    Route("/api/换绑", api_换绑入口, methods=["GET", "POST"]),
    Route("/api/rebind", api_换绑入口, methods=["GET", "POST"]),
    Route("/api/观测点/换绑", api_换绑入口, methods=["GET", "POST"]),
    Route("/api/观测点/rebind", api_换绑入口, methods=["GET", "POST"]),
    Route("/api/观测点换绑/执行", api_换绑入口, methods=["POST"]),
    Route("/api/换绑/执行", api_换绑入口, methods=["POST"]),
    Route("/api/换绑/跑", api_换绑入口, methods=["POST"]),
    Route("/api/观测点换绑/只读", api_换绑只读, methods=["GET"]),
    Route("/api/换绑/只读", api_换绑只读, methods=["GET"]),
    Route("/api/换绑只读接口", api_换绑只读, methods=["GET"]),
    Route("/api/换绑只读", api_换绑只读, methods=["GET"]),
    Route("/api/rebind/view", api_换绑只读, methods=["GET"]),
    Route("/api/观测点换绑/记录", api_换绑记录, methods=["GET"]),
    Route("/api/换绑记录", api_换绑记录, methods=["GET"]),
    Route("/api/换绑列表", api_换绑记录, methods=["GET"]),
    Route("/api/rebind/records", api_换绑记录, methods=["GET"]),
    Route("/api/换绑归档", api_换绑归档, methods=["GET"]),
    Route("/api/换绑/归档", api_换绑归档, methods=["GET"]),
    Route("/api/空桩", api_空桩),
]
