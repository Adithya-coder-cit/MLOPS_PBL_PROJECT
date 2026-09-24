"""Per-edge data lineage: every routing-graph edge must be traceable back
to the source GTFS-like record(s) it was built from, and every derived
(not directly-sourced) value must be explicitly marked as such.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FieldLineage:
    value_name: str
    source_dataset: str
    source_record: str
    transformation: str
    is_derived: bool

    def to_dict(self) -> dict:
        return {
            "value_name": self.value_name, "source_dataset": self.source_dataset,
            "source_record": self.source_record, "transformation": self.transformation,
            "is_derived": self.is_derived,
        }


@dataclass
class EdgeLineage:
    edge_id: str
    fields: list[FieldLineage] = field(default_factory=list)

    def add(self, value_name: str, source_dataset: str, source_record: str, transformation: str,
            is_derived: bool) -> None:
        self.fields.append(FieldLineage(value_name, source_dataset, source_record, transformation, is_derived))

    def to_dict(self) -> dict:
        return {"edge_id": self.edge_id, "fields": [f.to_dict() for f in self.fields]}
