from __future__ import annotations

from app.schemas.media import ChartSpec

# Code-rendered charts. The LLM never invents numbers — a ChartSpec must carry
# source_ids tying every series back to VERIFIED knowledge-pack data.


class ChartDataError(ValueError):
    pass


def validate_spec(spec: ChartSpec) -> None:
    if not spec.labels or not spec.values:
        raise ChartDataError("chart needs labels and values")
    if len(spec.labels) != len(spec.values):
        raise ChartDataError("labels/values length mismatch")
    if not spec.source_ids:
        raise ChartDataError("chart values must cite source_ids (VERIFIED data only)")


def render_chart(spec: ChartSpec, out_path: str, *, width: int = 1080, height: int = 1080) -> str:
    validate_spec(spec)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    from app.media.fonts import regular_font_path

    fp = regular_font_path()
    if fp:
        try:
            font_manager.fontManager.addfont(fp)
            matplotlib.rcParams["font.family"] = font_manager.FontProperties(fname=fp).get_name()
        except Exception:  # noqa: BLE001
            pass
    matplotlib.rcParams["axes.unicode_minus"] = False

    dpi = 100
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    accent = "#2f6df6"
    if spec.chart_type == "line":
        ax.plot(spec.labels, spec.values, marker="o", color=accent, linewidth=3)
    elif spec.chart_type == "pie":
        ax.pie(spec.values, labels=spec.labels, autopct="%1.0f%%")
        ax.axis("equal")
    else:
        ax.bar(spec.labels, spec.values, color=accent)
    if spec.title:
        ax.set_title(spec.title, fontsize=22, pad=16)
    if spec.chart_type != "pie":
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=14)
    fig.tight_layout()
    fig.savefig(out_path, facecolor="white")
    plt.close(fig)
    return out_path
