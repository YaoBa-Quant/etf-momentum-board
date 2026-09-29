from __future__ import annotations

import math


def calc_slope_momentum_from_closes(closes: list[float], annual_days: int = 252) -> float | None:
    if len(closes) < 2:
        return None

    if any(close is None or close <= 0 for close in closes):
        return None

    y = [math.log(close) for close in closes]
    x = list(range(len(y)))
    if len(y) == 1:
        return None

    w = [1.0 + index / (len(y) - 1) for index in range(len(y))]
    weight_sum = sum(w)
    x_bar = sum(weight * value for weight, value in zip(w, x)) / weight_sum
    y_bar = sum(weight * value for weight, value in zip(w, y)) / weight_sum

    sxx = sum(weight * ((value - x_bar) ** 2) for weight, value in zip(w, x))
    if sxx <= 0:
        return None

    slope = sum(weight * (x_value - x_bar) * (y_value - y_bar) for weight, x_value, y_value in zip(w, x, y)) / sxx
    intercept = y_bar - slope * x_bar
    y_hat = [intercept + slope * value for value in x]

    ss_res = sum(weight * ((y_value - fitted) ** 2) for weight, y_value, fitted in zip(w, y, y_hat))
    ss_tot = sum(weight * ((y_value - y_bar) ** 2) for weight, y_value in zip(w, y))
    if ss_tot <= 1e-12:
        r_squared = 0.0
    else:
        r_squared = max(0.0, min(1.0, 1.0 - ss_res / ss_tot))

    slope_annualized = math.exp(slope * annual_days) - 1.0
    return float(slope_annualized * r_squared)
