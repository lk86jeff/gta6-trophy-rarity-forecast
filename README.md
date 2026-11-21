# GTA VI trophy rarity forecaster

Entry for make.fun `gta6-trophy-rarity-forecast-01`. `main.py` (Python 3.13, standard library only) reads `/input/<id>.in` and writes `/output/<id>.out`: five logit-scale quantiles per trophy, from a damped, tier-shrunk Theil-Sen trend of each trophy's logit earn rate against log time over the distinct Exophase reads of the last 30 hours.
