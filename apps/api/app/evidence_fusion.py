"""Deterministic, side-effect-free fusion. No identity probability or master writes."""

from uuid import UUID

from app.fusion_schemas import FusionInput, FusionResult, UnitCandidate
from app.identifier_values import IdentifierType, normalize_identifier


def fuse_evidence(data: FusionInput) -> FusionResult:
    visual = data.visual
    model_status = visual.status if visual else "UNKNOWN_MODEL"
    # Uncalibrated rankings remain visible as model evidence but never select physical units.
    models = tuple(c.device_model_id for c in visual.candidates) if visual else ()
    accepted = (
        set(models)
        if visual and visual.calibrated and (visual.status == "KNOWN_MODEL_CANDIDATE")
        else set()
    )
    reasons: set[str] = set()
    strong_sets: list[set[UUID]] = []
    weak_ids: set[UUID] = set()
    details: dict[UUID, set[str]] = {u.asset_id: set() for u in data.units}
    for evidence in data.identifiers:
        candidate = evidence.candidate
        kind = candidate.kind
        if kind not in {"SERIAL_NUMBER", "MAC_LAN", "MAC_WLAN"}:
            reasons.add("IDENTIFIER_TYPE_NOT_UNIT_IDENTITY")
            continue
        try:
            value = normalize_identifier(IdentifierType(kind), candidate.raw_value)
        except ValueError:
            reasons.add("INVALID_IDENTIFIER")
            continue
        if value != candidate.normalized_value:
            reasons.add("INCONSISTENT_IDENTIFIER")
            continue
        if kind != "SERIAL_NUMBER" and (int(value[:2], 16) & 1 or value == "00:00:00:00:00:00"):
            reasons.add("NON_DEVICE_MAC_ADDRESS")
            continue
        scoped = kind != "SERIAL_NUMBER" or evidence.manufacturer_id is not None
        checked = evidence.human_checked and scoped
        if not scoped:
            reasons.add("SERIAL_MANUFACTURER_REQUIRED")
        if not evidence.human_checked:
            reasons.add("LABEL_REVIEW_REQUIRED")
        matches: set[UUID] = set()
        trusted: set[UUID] = set()
        for unit in data.units:
            if (
                kind == "SERIAL_NUMBER"
                and evidence.manufacturer_id is not None
                and (unit.manufacturer_id != evidence.manufacturer_id)
            ):
                continue
            claims = [c for c in unit.claims if c.kind == kind and c.value == value]
            if claims:
                matches.add(unit.asset_id)
                details[unit.asset_id].add("IDENTIFIER_MATCH")
                if any(c.verification == "VERIFIED" for c in claims):
                    trusted.add(unit.asset_id)
                if any(c.verification == "DISPUTED" for c in claims):
                    reasons.add("DISPUTED_MASTER_CLAIM")
        weak_ids.update(matches)
        if checked:
            # Even an unmatched checked identifier must not silently disappear when another matches.
            strong_sets.append(matches)
            if not matches:
                reasons.add("CHECKED_IDENTIFIER_UNMATCHED")
            if matches != trusted:
                reasons.add("MASTER_CLAIM_REVIEW_REQUIRED")
    identity_ids = set().union(*strong_sets) if strong_sets else set()
    conflict = bool(identity_ids) and len(strong_sets) > 1 and not set.intersection(*strong_sets)
    if conflict:
        reasons.add("IDENTIFIERS_DISAGREE")
    collision = any(len(ids) > 1 for ids in strong_sets)
    if collision:
        reasons.add("IDENTIFIER_COLLISION")
    selected = identity_ids | weak_ids
    visual_units = [u for u in data.units if not u.archived and u.device_model_id in accepted]
    local_units = [
        u
        for u in visual_units
        if data.observed_location_id is not None
        and u.current_location_id == data.observed_location_id
    ]
    selected.update(u.asset_id for u in (local_units or visual_units))
    # Checked but unmatched evidence must not fall back to model/location unit guesses.
    if strong_sets:
        selected = identity_ids | weak_ids if identity_ids else set()
    units = [u for u in data.units if u.asset_id in selected]
    for unit in units:
        notes = details[unit.asset_id]
        if unit.device_model_id in accepted:
            notes.add("MODEL_CANDIDATE_ONLY")
        elif unit.asset_id in identity_ids and accepted:
            conflict = True
            notes.add("MODEL_IDENTIFIER_CONFLICT")
        if unit.archived:
            notes.add("ARCHIVED_UNIT_REQUIRES_REVIEW")
        if data.observed_location_id is not None:
            if unit.current_location_id == data.observed_location_id:
                notes.add("OFFICIAL_LOCATION_SUPPORT_ONLY")
            elif unit.current_location_id is not None and unit.asset_id in identity_ids:
                # Backdated observation cannot prove a conflict with a later official placement.
                if unit.location_verified_at and data.observed_at < unit.location_verified_at:
                    notes.add("OBSERVATION_PRECEDES_OFFICIAL_LOCATION")
                else:
                    conflict = True
                    notes.add("OFFICIAL_LOCATION_CONFLICT")
        for event, label in (
            (unit.latest_observation, "LATEST_OBSERVATION"),
            (unit.approved_location, "APPROVED_HISTORY"),
        ):
            if event is None:
                continue
            if event.observed_at > data.observed_at or (
                unit.location_verified_at and event.observed_at < unit.location_verified_at
            ):
                notes.add(label + "_STALE_OR_LATER")
            elif event.location_id != unit.current_location_id:
                notes.add(label + "_MASTER_MISMATCH")
                if unit.asset_id in identity_ids:
                    conflict = True
            elif event.location_id == data.observed_location_id:
                notes.add(label + "_SUPPORT_ONLY")
    # Location narrows model-only suggestions; all identifier collisions remain visible.
    units.sort(
        key=lambda u: (
            u.asset_id not in identity_ids,
            u.current_location_id != data.observed_location_id or data.observed_location_id is None,
            str(u.asset_id),
        )
    )
    if conflict:
        status = "CONFLICT"
    elif collision or len(units) > 1:
        status = "AMBIGUOUS"
    elif units:
        status = "PROBABLE_ASSET"
    else:
        status = "UNKNOWN"
        reasons.add("NO_UNIT_EVIDENCE")
    reasons.add("HUMAN_REVIEW_REQUIRED_NO_AUTO_VERIFICATION")
    return FusionResult(
        status=status,
        model_status=model_status,
        model_candidates=models,
        candidates=tuple(
            UnitCandidate(
                asset_id=u.asset_id,
                asset_version=u.asset_version,
                device_model_id=u.device_model_id,
                rank=i + 1,
                reasons=tuple(sorted(details[u.asset_id])),
            )
            for i, u in enumerate(units)
        ),
        reasons=tuple(sorted(reasons)),
        snapshot_at=data.snapshot_at,
        observed_at=data.observed_at,
    )
