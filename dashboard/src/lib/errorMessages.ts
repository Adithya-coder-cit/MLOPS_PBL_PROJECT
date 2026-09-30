import { ApiError } from '../api/client'

// User-facing copy for each backend error code — never a raw stack
// trace or exception string reaches the UI.
const MESSAGES: Record<string, string> = {
  invalid_input: 'Check the highlighted fields and try again.',
  unknown_stop: "That stop isn't in the current dataset. Pick one from the list.",
  unknown_route: "That route isn't in the current dataset.",
  unreachable_destination: "We couldn't find a suitable route for this journey.",
  no_path_found: "We couldn't find a suitable route for this journey.",
  invalid_route: 'That route could not be processed.',
  model_unavailable: 'RouteWise is temporarily unavailable. Please try again.',
  no_production_model: 'No production model is available yet — this system is running on a development model.',
  inference_failure: 'RouteWise is temporarily unavailable. Please try again.',
  internal_error: 'RouteWise is temporarily unavailable. Please try again.',
  network_error: 'RouteWise is temporarily unavailable. Please try again.',
  unknown_error: 'Something unexpected happened. Try again.',
}

export function friendlyErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return MESSAGES[error.code] ?? MESSAGES.unknown_error
  }
  return MESSAGES.unknown_error
}
