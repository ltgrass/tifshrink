# -*- coding: utf-8 -*-
"""tifshrink.gui - 图形界面 (tkinter, 标准库; 无额外 GUI 依赖)

界面只做一件事: 让用户选一幅影像、填一个输出分辨率、看到"会输出多大", 然后压缩。
压缩在工作线程里跑, 进度经 after() 回主线程刷新, 取消在块边界生效。
"""
from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import config as C
from . import core, downscale
from .core import TifShrinkError

# 计划与测试里用的名字; 实现放在 core, 避免与 cli 各写一份
suggest_output_path = core.default_output_path


def format_bytes(n: int) -> str:
    """1024 进制, 1 位小数"""
    units = ("B", "KB", "MB", "GB", "TB")
    v = float(n)
    for u in units:
        if v < 1024 or u == units[-1]:
            return f"{v:.1f} {u}"
        v /= 1024.0
    return f"{v:.1f} TB"


def estimate_seconds(plan, pixels_per_sec: float = 8_000_000.0) -> float:
    """粗略耗时预估: 按需读取的源层像元数折算

    实测基准: DOM.tif 源层 23.5M 像元耗时 1.9 s (约 12M 像元/秒), 这里取 8M
    作保守值 —— 宁可把等待说长一点。
    """
    return float(plan.source_pixels) / max(1.0, pixels_per_sec)


def format_seconds(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} 秒"
    return f"{seconds / 60:.0f} 分钟"


def build_hints(meta, plan, uncompressed_bytes: int,
                cell_size_m: float = C.DEFAULT_CELL_SIZE_M) -> list:
    """提示类信息 (黄色, 不阻断) —— 全部来自可算出的量, 不做猜测

    包含 plan.notes (例如源层因像元上限退化), 因为它正是"为什么变慢了/精度变粗了"
    的解释, 只打在 CLI 上而界面上不显示, 用户就无从理解。
    """
    hints: list = [n for n in plan.notes if "无概览" not in n]
    if uncompressed_bytes > C.WARN_UNCOMPRESSED_MB * 1024 * 1024:
        hints.append(f"输出体积较大 (> {C.WARN_UNCOMPRESSED_MB:.0f} MB), 上传可能较慢; "
                     f"可把输出分辨率填大一些")
    per_cell = (cell_size_m / plan.out_res) ** 2 if plan.out_res else 0
    if per_cell < C.MIN_SUBPIXELS_PER_CELL:
        hints.append(f"压缩过狠: 每个 {cell_size_m:g} m 作业单元只剩 {per_cell:.0f} 个像元 "
                     f"(建议 < {C.MIN_SUBPIXELS_PER_CELL}); 请把输出分辨率填小一些")
    if meta.count < 4:
        hints.append(f"影像只有 {meta.count} 个波段, 缺少 NIR/RE, 压缩后仍无法做真实反演")
    if not meta.overviews:
        hints.append(f"影像无概览, 将按原分辨率逐块读取, 预计约 "
                     f"{format_seconds(estimate_seconds(plan))} "
                     f"(把同名 .ovr 放在一起可显著加速)")
    return hints


def summary_lines(meta, plan, uncompressed_bytes: int, src_bytes: int | None = None,
                  cell_size_m: float = C.DEFAULT_CELL_SIZE_M) -> list:
    """信息区文案 (原始 / 输出 / 每像元细像元数 / 每作业单元像元数)"""
    per_cell = (cell_size_m / plan.out_res) ** 2 if plan.out_res else 0
    original = f"原始：{meta.res_x * 1000:.2f} mm · {meta.width}×{meta.height}"
    if src_bytes:
        original += f" · {format_bytes(src_bytes)}"
    original += f" · {meta.count} 波段"
    return [
        original,
        f"输出：{plan.out_res:.4f} m · {plan.out_width}×{plan.out_height} · "
        f"预计 ≤ {format_bytes(uncompressed_bytes)}（实测通常再小 1.5~2.5 倍）",
        f"       每个输出像元由 {plan.sub_pixels} 个细像元均值得到",
        f"       每个 {cell_size_m:g} m 作业单元含 {per_cell:.0f} 个像元",
    ]


def resolve_overwrite(dst, ask) -> bool | None:
    """目标已存在时问用户是否覆盖 (在主线程调用)

    返回 True/False 作为 overwrite 标志; None 表示用户放弃本次压缩。
    必须在主线程调用: tkinter 的对话框不支持从工作线程弹出。
    """
    if not Path(dst).exists():
        return False
    if ask(f"目标文件已存在：\n{dst}\n\n是否覆盖？"):
        return True
    return None


class App:
    """主窗口"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.meta = None
        self.plan = None
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None

        root.title("施肥系统 · 影像压缩工具")
        root.minsize(620, 340)
        self._build()
        self._refresh()

    # ---------------- 构建界面 ----------------
    def _build(self):
        pad = dict(padx=8, pady=4)
        self.src_var = tk.StringVar()
        self.target_var = tk.StringVar(value=str(C.DEFAULT_TARGET_M))
        self.dst_var = tk.StringVar()

        frm = ttk.Frame(self.root, padding=12)
        frm.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="原始影像").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.src_var).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="选择…", command=self._pick_src).grid(row=0, column=2, **pad)

        ttk.Label(frm, text="输出分辨率").grid(row=1, column=0, sticky="w", **pad)
        row1 = ttk.Frame(frm)
        row1.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)
        ttk.Entry(row1, textvariable=self.target_var, width=10).pack(side="left")
        ttk.Label(row1, text=f"米   （作业尺度 {C.DEFAULT_CELL_SIZE_M:g} m）").pack(side="left")

        self.info = ttk.Label(frm, text="", justify="left", foreground="#333")
        self.info.grid(row=2, column=0, columnspan=3, sticky="w", **pad)

        self.hint_label = ttk.Label(frm, text="", justify="left", foreground="#a06000")
        self.hint_label.grid(row=3, column=0, columnspan=3, sticky="w", **pad)

        ttk.Label(frm, text="保存到").grid(row=4, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.dst_var).grid(row=4, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="另存…", command=self._pick_dst).grid(row=4, column=2, **pad)

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=3, pady=(10, 4))
        self.start_btn = ttk.Button(btns, text="开始压缩", command=self._start)
        self.start_btn.pack(side="left", padx=6)
        self.cancel_btn = ttk.Button(btns, text="取消", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)

        self.bar = ttk.Progressbar(frm, mode="determinate")
        self.bar.grid(row=6, column=0, columnspan=3, sticky="ew", **pad)
        self.status = ttk.Label(frm, text="请选择一幅 GeoTIFF 影像")
        self.status.grid(row=7, column=0, columnspan=3, sticky="w", **pad)

        self.target_var.trace_add("write", lambda *_: self._refresh())

    # ---------------- 交互 ----------------
    def _pick_src(self):
        path = filedialog.askopenfilename(
            title="选择影像", filetypes=[("GeoTIFF", "*.tif *.tiff"), ("所有文件", "*.*")])
        if path:
            self.src_var.set(path)
            self._refresh()

    def _pick_dst(self):
        path = filedialog.asksaveasfilename(title="保存为", defaultextension=".tif",
                                            initialfile=Path(self.dst_var.get()).name)
        if path:
            self.dst_var.set(path)

    def _refresh(self):
        """换影像或改分辨率 -> 重算方案并刷新全部文案"""
        self.meta = self.plan = None
        src = Path(self.src_var.get()) if self.src_var.get() else None
        target = self._target()
        if src is None or not src.exists():
            self.info.config(text="")
            self.dst_var.set("")
            return self._set_hints([])
        try:
            self.meta = core.read_meta(src)
            if target is None:
                return self._set_hints([])
            self.plan = core.plan_downscale(self.meta, target)
        except TifShrinkError as e:
            self.info.config(text="")
            self.dst_var.set("")
            return self._set_hints([f"[无法处理] {e.message}"])

        m, p = self.meta, self.plan
        est = downscale.estimate_uncompressed_bytes(p, m.count, m.dtype)
        self.info.config(text="\n".join(
            summary_lines(m, p, est, src_bytes=Path(src).stat().st_size)))
        self.dst_var.set(str(suggest_output_path(src, p.out_res)))
        self._set_hints(build_hints(m, p, est))

    def _set_hints(self, hints):
        self.hint_label.config(text="\n".join(hints))
        return hints

    def _target(self):
        try:
            v = float(self.target_var.get())
            return v if v > 0 else None
        except ValueError:
            return None

    # ---------------- 压缩 ----------------
    def _start(self):
        if self.plan is None or self.meta is None:
            messagebox.showwarning("无法开始", "请先选择影像并填写合法的输出分辨率")
            return
        dst = self.dst_var.get().strip()
        if not dst:
            messagebox.showwarning("无法开始", "请指定保存路径")
            return
        self.cancel_event.clear()
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.bar.config(maximum=1, value=0)
        self.status.config(text="正在压缩…")
        # 覆盖确认必须在主线程问 (tkinter 对话框不支持工作线程), 且 target 也在此定下,
        # 避免工作线程去读 Tk 变量
        self.target = self._target()
        self.overwrite = False
        decision = resolve_overwrite(dst, lambda msg: messagebox.askyesno("确认覆盖", msg))
        if decision is None:
            self.status.config(text="已取消（目标文件已存在）")
            return self._reset_buttons()
        self.overwrite = decision
        self.t0 = time.time()
        self.worker = threading.Thread(target=self._run, args=(self.src_var.get(), dst),
                                       daemon=True)
        self.worker.start()

    def _cancel(self):
        self.cancel_event.set()
        self.status.config(text="正在取消（在本分块结束时停止）…")

    def _run(self, src: str, dst: str):
        """工作线程: 只碰数据, 界面更新一律经 after() 回主线程"""
        try:
            res = downscale.downscale(
                src, dst, self.target, overwrite=self.overwrite,
                progress=lambda d, t: self.root.after(0, self._on_progress, d, t),
                cancel=self.cancel_event.is_set)
        except TifShrinkError as e:
            self.root.after(0, self._on_error, e.code, e.message)
            return
        except Exception as e:                                  # noqa: BLE001
            self.root.after(0, self._on_error, "UNEXPECTED", f"{e.__class__.__name__}: {e}")
            return
        self.root.after(0, self._on_done, res)

    def _on_progress(self, done: int, total: int):
        self.bar.config(maximum=total, value=done)
        elapsed = time.time() - self.t0
        eta = elapsed / done * (total - done) if done else 0.0
        self.status.config(text=f"正在压缩… {done}/{total} 块  "
                                f"已用 {format_seconds(elapsed)}  "
                                f"剩余约 {format_seconds(eta)}")

    def _on_done(self, res: dict):
        self._reset_buttons()
        self.bar.config(value=self.bar["maximum"])
        self.status.config(
            text=f"完成：{res['dst']}（{format_bytes(res['bytes_out'])}，"
                 f"耗时 {res['elapsed_sec']} s）")
        messagebox.showinfo("压缩完成",
                            f"已生成：\n{res['dst']}\n\n"
                            f"{res['out_width']}×{res['out_height']} 像元, "
                            f"分辨率 {res['out_res']} m\n"
                            f"体积 {format_bytes(res['bytes_out'])}\n\n"
                            "请把这个文件上传到 OBS，再把地址填进追肥推荐接口。")

    def _on_error(self, code: str, message: str):
        self._reset_buttons()
        if code == "CANCELLED":
            # 取消是用户的正常操作, 不该弹成"失败"
            self.status.config(text="已取消（未完成的中间文件保留为 .partial，可自行删除）")
            return
        self.status.config(text="失败")
        messagebox.showerror("压缩失败", message)

    def _reset_buttons(self):
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")


def main() -> int:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
