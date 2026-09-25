import type { ModelMetadataSchema } from '../../api/types'
import './ModelLifecycleBadge.css'

export function ModelLifecycleBadge({ metadata }: { metadata: ModelMetadataSchema }) {
  return (
    <span className="rw-model-badge-group" title={metadata.model_source_warning ?? undefined}>
      <span className="rw-model-badge-group__name">
        {metadata.model_name} v<span className="data">{metadata.model_version}</span>
      </span>
      <span
        className={`rw-model-badge-group__stage ${
          metadata.is_production_model ? 'rw-model-badge-group__stage--production' : 'rw-model-badge-group__stage--candidate'
        }`}
      >
        {metadata.lifecycle_stage ?? 'Unknown'}
      </span>
    </span>
  )
}
