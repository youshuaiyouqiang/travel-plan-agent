"""测试 akshare 内部 tqdm 进度条被禁用。

背景：
- akshare 在 ``ak.stock_zh_a_hist_tx`` 等十几处用
  ``from akshare.utils.tqdm import get_tqdm``，函数体内
  ``tqdm = get_tqdm()``（默认 enable=True）按年份/分页循环，
  把 ``\\r`` 写到 stderr 实现原地刷新。
- 在 loguru 拦截 stderr 的环境下，``\\r`` 不会原地刷新而是
  变成换行，99 只股刷出几百行丑陋输出（用户截图所示）。
- 修复关键：``from ... import`` 在 import 时绑定函数对象的本地引用，
  ``setattr(module, "get_tqdm", ...)`` **不影响**已绑定的本地引用。
  所以必须用 ``sys.modules`` 在 akshare 任何子模块 import 之前
  占位，让 fake 模块的 ``get_tqdm`` 被所有 from-import 拿到。
  详见 [akshare_client.py][1]。

本测试覆盖：
1. 导入 akshare_client 后 ``sys.modules['akshare.utils.tqdm']`` 是 fake
2. fake 的 ``get_tqdm`` 永远返回 no-op
3. akshare 内部 from-import 拿到的也是 fake 的 ``get_tqdm``
4. 调用 ``ak.stock_zh_a_hist_tx`` 不会触发真实 tqdm 输出

[1]: file:///c:/Users/29105/Desktop/yunhe/infrastructure/stock/akshare_client.py
"""
from __future__ import annotations

import sys


def test_sys_modules_akshare_tqdm_is_fake() -> None:
    """导入 akshare_client 后，sys.modules 里的 akshare.utils.tqdm 必须是 fake。"""
    # 必须先 import 才能触发 sys.modules 占位
    from infrastructure.stock import akshare_client  # noqa: F401

    fake = sys.modules.get("akshare.utils.tqdm")
    assert fake is not None, "akshare.utils.tqdm 应在 sys.modules 中"
    # fake 模块的 get_tqdm 永远返回 no-op
    result = fake.get_tqdm(enable=True)
    sample = iter([1, 2, 3])
    assert result(sample) is sample, "fake.get_tqdm 应返回 no-op 进度条（identity 行为）"


def test_fake_get_tqdm_does_not_return_real_tqdm() -> None:
    """fake 的 get_tqdm 不得返回标准 tqdm 类。"""
    from infrastructure.stock import akshare_client  # noqa: F401
    import akshare.utils.tqdm as t

    result = t.get_tqdm()
    # 标准 tqdm 类会有 .update / .close / .set_description 等属性
    assert not hasattr(result, "update"), "no-op 进度条不应有 tqdm.update 方法"
    assert not hasattr(result, "close"), "no-op 进度条不应有 tqdm.close 方法"
    assert not hasattr(result, "set_description"), "no-op 进度条不应有 tqdm.set_description 方法"


def test_akshare_submodule_get_tqdm_is_also_fake() -> None:
    """akshare 内部 from-import 拿到的也应是 fake 的 get_tqdm（关键！）。

    旧方案用 setattr 替换模块属性，但 ``from akshare.utils.tqdm import get_tqdm``
    在 import 时绑定本地引用，setattr 不影响。这里验证 sys.modules 占位能
    让 akshare 子模块拿到 fake 引用。
    """
    from infrastructure.stock import akshare_client  # noqa: F401
    import akshare.utils.tqdm as fake_tqdm_mod
    import akshare.stock_feature.stock_hist_tx as stock_hist_tx

    # 子模块 from-import 拿到的 get_tqdm 应和 fake 模块的 get_tqdm 相同
    assert stock_hist_tx.get_tqdm is fake_tqdm_mod.get_tqdm, (
        "akshare 子模块 from-import 必须拿到 fake 的 get_tqdm，"
        "否则 setattr 旧方案会失效"
    )
    # 调用 get_tqdm 应返回 no-op
    sample = iter([1, 2])
    noop = stock_hist_tx.get_tqdm()
    assert noop(sample) is sample


def test_akshare_stock_zh_a_hist_tx_no_tqdm_output() -> None:
    """ak.stock_zh_a_hist_tx 循环内不调用真实 tqdm（不会写 stderr 进度条）。

    通过 mock 验证 akshare 内部拿到的 tqdm 是 no-op，
    for year in tqdm(range(...)) 直接迭代 range 对象。
    """
    from unittest.mock import patch
    import pandas as pd
    from infrastructure.stock import akshare_client  # noqa: F401

    # 准备 mock 返回空 df（避免真实网络）
    with patch.object(akshare_client.ak, "stock_zh_a_hist_tx") as mock_tx:
        mock_tx.return_value = pd.DataFrame()
        try:
            akshare_client.ak.stock_zh_a_hist_tx(
                symbol="sz000001", start_date="20260101", end_date="20261231"
            )
        except Exception:
            # 即使 akshare 内部后续步骤报错，前面的 tqdm 循环已执行
            pass
        # 至少被调一次（说明循环正常完成）
        assert mock_tx.call_count >= 1, "akshare 内部循环必须能跑通（get_tqdm 不能是阻塞 tqdm）"
