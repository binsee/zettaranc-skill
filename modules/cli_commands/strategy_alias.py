"""CLI 中文别名 → screener 英文 criteria 的统一映射。"""

STRATEGY_ALIAS: dict[str, str] = {
    "B1": "b1",
    "B2": "b2_breakout",
    "B3": "b3_consensus",
    "完美图形": "perfect",
    "超级B1": "super_b1",
    "长安战法": "changan",
    "建仓波": "build_wave",
    "吸筹": "xishou",
    "安全": "safe",
    "超跌": "oversold",
    "突破": "breakout",
    "牵牛": "bull_rope",
    "牛绳": "bull_rope",
    "沙漏": "sandglass_perfect",
    "沙漏评分": "sandglass_perfect",
    "量比战法": "volume_ratio_super",
}

STRATEGY_CHOICES: list[str] = list(STRATEGY_ALIAS.keys())
