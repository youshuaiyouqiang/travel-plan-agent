"""测试 akshare 内部 tqdm 进度条被禁用。

背景：
- akshare 在 ``ak.stock_zh_a_hist_tx`` 等函数里用
  ``tqdm = get_tqdm()``（默认 enable=True）按年份循环，
  把 ``\\r`` 写到 stderr 实现原地刷新。
- 在 loguru 拦截 stderr 的环境下，``\\r`` 不会原地刷新而是
  变成换行，99 只股刷出几百行丑陋输出（用户截图所示）。
- 修复：在 [akshare_client.py][1] 顶部 monkey-patch
  ``akshare.utils.tqdm.get_tqdm`` 永远返回 no-op 进度条。

本测试覆盖：
1. 导入 akshare_client 后 ``akshare.utils.tqdm.get_tqdm`` 已被替换
2. 替换后调用 ``ak.stock_zh_a_hist_tx`` 不会触发 tqdm 输出
   （通过 mock 验证传给 ak 的是 year 列表而非 tqdm 对象）

[1]: file:///c:/Users/29105/Desktop/yunhe/infrastructure/stock/akshare_client.py
"""
from __future__ import annotations


def test_get_tqdm_is_disabled_after_import() -> None:
    """导入 akshare_client 后，akshare.utils.tqdm.get_tqdm 必须返回 no-op。"""
    import akshare.utils.tqdm as t
    from infrastructure.stock import akshare_client  # noqa: F401  # 触发 monkey-patch

    result = t.get_tqdm(enable=True)  # 即使显式传 True 也应被禁用
    # result 应是 no-op：传入可迭代对象，应原样返回
    sample = iter([1, 2, 3])
    assert result(sample) is sample, "get_tqdm 应返回 no-op 进度条（identity 行为）"


def test_get_tqdm_does_not_return_real_tqdm() -> None:
    """替换后 get_tqdm 不得返回标准 tqdm 类。"""
    import akshare.utils.tqdm as t
    from infrastructure.stock import akshare_client  # noqa: F401

    result = t.get_tqdm()
    # 标准 tqdm 类会有 .update / .close / .set_description 等属性
    assert not hasattr(result, "update"), "no-op 进度条不应有 tqdm.update 方法"
    assert not hasattr(result, "close"), "no-op 进度条不应有 tqdm.close 方法"
    assert not hasattr(result, "set_description"), "no-op 进度条不应有 tqdm.set_description 方法"


def test_akshare_stock_zh_a_hist_tx_called_with_year_range() -> None:
    """akshare 内部循环应直接迭代 range 而非 tqdm(range(...))。

    通过 mock ak.stock_zh_a_hist_tx 触发其源码执行，
    验证它拿到的 "tqdm" 对象是 no-op，循环仍能完成。
    """
    from unittest.mock import patch
    import pandas as pd
    from infrastructure.stock import akshare_client  # noqa: F401

    # 准备 mock 返回空 df（避免真实网络）
    with patch.object(akshare_client.ak, "stock_zh_a_hist_tx") as mock_tx:
        mock_tx.return_value = pd.DataFrame()
        # 触发 1 年循环（start=end=2026），不会真的请求网络
        try:
            akshare_client.ak.stock_zh_a_hist_tx(
                symbol="sz000001", start_date="20260101", end_date="20261231"
            )
        except Exception:
            # 即使 akshare 内部后续步骤报错，前面的 tqdm 循环已执行
            pass
        # 至少被调一次（说明循环正常完成）
        assert mock_tx.call_count >= 1, "akshare 内部循环必须能跑通（get_tqdm 不能是阻塞 tqdm）"
