import { ApiError } from '../api/client'

// User-facing copy for each backend error code — never a raw stack
// trace or exception string reaches the UI.
const MESSAGES: Record<string, string> = {
  invalid_input: 'Check the highlighted fields and try again.',
  unknown_stop: "That stop isn't in the current dataset. Pick one from the list.",
  unknown_route: "That route isn't in the current dataset.",
  unreachable_destination: 'No route connects these two stops in the current network.',
  no_path_found: 'No path was found between these stops.',
  invalid_route: 'That route could not be processed.',
  model_unavailable: 'The prediction model is temporarily unavailable. Route search is paused until it reloads.',
  no_production_model: 'No production model is available yet — this system is running on a development model.',
  inference_failure: 'The prediction model failed to process this request. Try again in a moment.',
  internal_error: 'Something went wrong on the server. Try again in a moment.',
  network_error: "Can't reach the RouteWise API. Check that the backend is running.",
  unknown_error: 'Something unexpected happened. Try again.',
}

export function friendlyErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return MESSAGES[error.code] ?? MESSAGES.unknown_error
  }
  return MESSAGES.unknown_error
}
