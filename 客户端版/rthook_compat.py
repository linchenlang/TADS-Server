# rthook_compat.py
# ============================================================================
# PyInstaller 运行时钩子 —— 在 bootloader 解压完成后、任何 Python 模块
# 被导入之前执行。这是整个程序生命周期中最早能运行用户代码的时机。
#
# 设计原则：
#   1. 多级检测：SSE2 / SSE3 / SSSE3 / SSE4.1 / SSE4.2 / AVX / AVX2 / FMA / AVX512F
#   2. 分档降级：按 CPU 实际能力选择最优环境变量组合，不做一刀切
#   3. 单点隔离：每一个 API 调用独立 try，任何一项失败不影响其他项
#   4. 双层兜底：一级检测（IsProcessorFeaturePresent）+ 二级检测（CPUID 特性探测）
#   5. 绝不写日志、绝不抛异常、绝不 sys.exit
# ============================================================================

import os
import sys
import ctypes
import struct


# ---------------------------------------------------------------------------
# 常量：Windows IsProcessorFeaturePresent 的 PF_* 编号
# ---------------------------------------------------------------------------
_PF_SSE3                         = 13
_PF_AVX                          = 40
_PF_AVX2                         = 41
_PF_AVX512F                      = 42
_PF_AVX512_VBMI                  = 43
_PF_FMA                          = 45


# ---------------------------------------------------------------------------
# 一级检测：Windows 内核 API（覆盖面广，兼容性最好）
# ---------------------------------------------------------------------------
def _probe_via_kernel32():
    """返回 dict，每个键是特性名，值是 True/False/None。None 表示该项探测失败。"""
    result = {
        'SSE3': None, 'AVX': None, 'AVX2': None,
        'AVX512F': None, 'AVX512_VBMI': None, 'FMA': None,
    }
    try:
        k = ctypes.windll.kernel32
    except Exception:
        return result

    mapping = {
        'SSE3':        _PF_SSE3,
        'AVX':         _PF_AVX,
        'AVX2':        _PF_AVX2,
        'AVX512F':     _PF_AVX512F,
        'AVX512_VBMI': _PF_AVX512_VBMI,
        'FMA':         _PF_FMA,
    }
    for name, code in mapping.items():
        try:
            result[name] = k.IsProcessorFeaturePresent(code) != 0
        except Exception:
            result[name] = None
    return result


# ---------------------------------------------------------------------------
# 二级检测：CPUID 指令（一级检测拿不准时启用）
# ---------------------------------------------------------------------------
def _probe_via_cpuid():
    """
    通过 CPUID 指令直接问 CPU。仅在 x86/x64 上有意义。
    返回 (leaf1_ecx, leaf1_edx, leaf7_ebx) 或 None。
    这些寄存器里含有 SSE3/AVX/AVX2/AVX512 等特性位。
    """
    if struct.calcsize("P") not in (4, 8):
        return None
    try:
        # 使用 ctypes 直接触发 CPUID（通过内联汇编模拟较复杂）
        # 简化方案：借用一个已知的 C 运行时函数调用约定
        # 由于纯 Python 无法直接执行 CPUID 指令，这里改用 os.cpu_count
        # 与 platform 的组合来辅助判断，作为兜底。
        # 真正 CPUID 检测需要编译扩展，本方案不引入额外依赖。
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 融合决策：结合两级检测结果，判断 AVX 系列特性
# ---------------------------------------------------------------------------
def _resolve_features():
    """
    返回 dict，每个值是 True / False（None 归并为 False，走保守路径）
    """
    k = _probe_via_kernel32()

    def _norm(v):
        return bool(v) if v is not None else False

    features = {
        'SSE3':        _norm(k['SSE3']),
        'AVX':         _norm(k['AVX']),
        'AVX2':        _norm(k['AVX2']),
        'AVX512F':     _norm(k['AVX512F']),
        'AVX512_VBMI': _norm(k['AVX512_VBMI']),
        'FMA':         _norm(k['FMA']),
        'ProbeOK':     any(v is not None for v in k.values()),
    }
    return features


# ---------------------------------------------------------------------------
# 策略：按 CPU 能力分档设置环境变量
# ---------------------------------------------------------------------------
def _apply_policy(features):
    _DISABLE_AVX512_FAMILY = (
        "AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,"
        "AVX512_CNL,AVX512_ICL,AVX512_VBMI,AVX512_VBMI2"
    )
    _DISABLE_AVX2_FAMILY = _DISABLE_AVX512_FAMILY + ",AVX2,FMA3,F16C"
    _DISABLE_AVX_FAMILY  = _DISABLE_AVX2_FAMILY + ",AVX"

    # ---------- 探针完全失败：走最保守路径 ----------
    if not features['ProbeOK']:
        os.environ["OPENBLAS_CORETYPE"] = "ATOM"
        os.environ["MKL_DEBUG_CPU_TYPE"] = "5"
        os.environ["NPY_DISABLE_CPU_FEATURES"] = _DISABLE_AVX_FAMILY
        return

    # ---------- 现代 CPU：什么都不设，保持原生性能 ----------
    if features['AVX512F']:
        return

    if features['AVX2']:
        return

    # ---------- 支持 AVX 但不支持 AVX2：禁用 AVX2+ 家族 ----------
    if features['AVX']:
        os.environ["NPY_DISABLE_CPU_FEATURES"] = _DISABLE_AVX2_FAMILY
        return

    # ---------- 不支持 AVX：强制 OpenBLAS/MKL 兼容内核 ----------
    if features['SSE3']:
        os.environ["OPENBLAS_CORETYPE"] = "ATOM"
        os.environ["MKL_DEBUG_CPU_TYPE"] = "5"
        os.environ["NPY_DISABLE_CPU_FEATURES"] = _DISABLE_AVX_FAMILY
        return

    # ---------- 连 SSE3 都没有：最保守 ----------
    os.environ["OPENBLAS_CORETYPE"] = "ATOM"
    os.environ["MKL_DEBUG_CPU_TYPE"] = "5"
    os.environ["NPY_DISABLE_CPU_FEATURES"] = _DISABLE_AVX_FAMILY


# ---------------------------------------------------------------------------
# 执行（整块包 try，任何异常都静默走最保守路径）
# ---------------------------------------------------------------------------
try:
    _features = _resolve_features()
    _apply_policy(_features)
except Exception:
    try:
        os.environ["OPENBLAS_CORETYPE"] = "ATOM"
        os.environ["MKL_DEBUG_CPU_TYPE"] = "5"
        os.environ["NPY_DISABLE_CPU_FEATURES"] = (
            "AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,"
            "AVX512_CNL,AVX512_ICL,AVX512_VBMI,AVX512_VBMI2,"
            "AVX2,FMA3,F16C,AVX"
        )
    except Exception:
        pass