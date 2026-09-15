/**
 * Pure helpers for presenting a model pick.
 *
 * These live outside GameCard so the rules can be unit-tested without
 * rendering anything. Both rules below were once wrong in the UI.
 */

import type { Prediction } from '@/api/types'

type PickInput = Pick<Prediction, 'predicted_side' | 'predicted_home_cover_prob'>

/** The team the model picked to cover. */
export function pickedTeam(
  game: { home_team: string; away_team: string },
  prediction: Pick<Prediction, 'predicted_side'>,
): string {
  return prediction.predicted_side === 'home' ? game.home_team : game.away_team
}

/**
 * The model's cover probability for the side it PICKED.
 *
 * `predicted_home_cover_prob` is always the HOME team's probability. GameCard
 * once printed it beside whichever team was picked, so an away pick showed the
 * home team's number: "WAS (33%)" for a game the model gave WAS 67%
 * (DEFECT-1, 2026-09-10).
 */
export function pickedSideProb(prediction: PickInput): number {
  return prediction.predicted_side === 'home'
    ? prediction.predicted_home_cover_prob
    : 1 - prediction.predicted_home_cover_prob
}
