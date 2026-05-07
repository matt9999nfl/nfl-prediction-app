import pandas as pd
import numpy as np

df = pd.read_csv('backtests/reports/20260503_103910_5ffdd7_predictions.csv')
decided = df.dropna(subset=['correct'])

print("=== PREDICTION DISTRIBUTION ===")
print(f"Total games:      {len(df)}")
print(f"Decided (W+L):    {len(decided)}")
print(f"Pushes:           {df['correct'].isna().sum()}")
print()
pred_home = (decided['predicted_side'] == 'home').sum()
pred_away = (decided['predicted_side'] == 'away').sum()
print(f"Predicted home:   {pred_home}  ({pred_home/len(decided):.1%})")
print(f"Predicted away:   {pred_away}  ({pred_away/len(decided):.1%})")
print()

print("=== PROBABILITY DISTRIBUTION ===")
print(decided['predicted_home_cover_prob'].describe().round(3))
print()

print("=== ACCURACY BY SIDE ===")
home_preds = decided[decided['predicted_side'] == 'home']
away_preds = decided[decided['predicted_side'] == 'away']
home_correct = home_preds['correct'].sum()
away_correct = away_preds['correct'].sum()
print(f"When model says HOME: {int(home_correct)}/{len(home_preds)} = {home_correct/len(home_preds):.1%}")
print(f"When model says AWAY: {int(away_correct)}/{len(away_preds)} = {away_correct/len(away_preds):.1%}")
print()

print("=== ACTUAL COVER RATES ===")
# What fraction of games does the HOME team actually cover?
actual_covers = decided['actual_home_covered'].dropna()
print(f"Home team actual cover rate: {actual_covers.mean():.3f}  ({actual_covers.sum():.0f}/{len(actual_covers)})")
print()

print("=== COVER RATE BY SEASON ===")
by_season = decided.groupby('season').agg(
    games=('correct', 'count'),
    model_wins=('correct', 'sum'),
    home_covered=('actual_home_covered', 'mean')
).round(3)
by_season['model_hit_rate'] = (by_season['model_wins'] / by_season['games']).round(3)
print(by_season)
print()

print("=== PROB DISTRIBUTION BY QUINTILE ===")
decided['prob_bin'] = pd.qcut(decided['predicted_home_cover_prob'], 5, labels=['Q1','Q2','Q3','Q4','Q5'])
print(decided.groupby('prob_bin', observed=True)['correct'].agg(['mean','count']).round(3))
print()

print("=== SPREAD SIGN VS PREDICTION ===")
# Check: when home is favored (spread < 0), does model mostly say home?
decided['home_favored'] = (decided['home_spread_close'] < 0)
ct = pd.crosstab(decided['home_favored'], decided['predicted_side'])
print(ct)
print()

print("=== SANITY: spread vs cover ===")
# If spread and cover are correlated in a leaky way, this would show
decided['abs_spread'] = decided['home_spread_close'].abs()
decided['spread_bin'] = pd.cut(decided['home_spread_close'], bins=[-30,-10,-6,-3,0,3,6,10,30])
sc = decided.groupby('spread_bin', observed=True)['actual_home_covered'].agg(['mean','count'])
print(sc.round(3))
