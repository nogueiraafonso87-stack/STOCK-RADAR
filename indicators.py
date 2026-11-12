"""Technical indicators with explicit flat/up/down edge cases."""
import numpy as np
import pandas as pd


def rsi(close, period=14):
    delta=close.astype(float).diff()
    gain=delta.clip(lower=0).ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    loss=(-delta.clip(upper=0)).ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    result=100-100/(1+gain/loss.replace(0,np.nan))
    result=result.mask((loss==0)&(gain>0),100)
    result=result.mask((gain==0)&(loss>0),0)
    return result.mask((gain==0)&(loss==0),50)
