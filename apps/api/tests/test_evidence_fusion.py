from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.evidence_fusion import fuse_evidence
from app.fusion_schemas import Claim, FusionInput, IdentityEvidence, LocationEvidence, UnitSnapshot
from app.ocr_schemas import IdentifierCandidate, ManualCorrection
from app.ocr_service import read_label
from app.recognition_schemas import ModelCandidate, SearchResult

NOW = datetime(2026, 10, 19, tzinfo=UTC)
MODEL, OTHER, MAKER, LOUNGE, LOBBY = (UUID(int=i) for i in range(1, 6))


def unit(n=10, **kw):
    return UnitSnapshot(
        asset_id=UUID(int=n), asset_version=1, device_model_id=MODEL, manufacturer_id=MAKER, **kw
    )


def claim(value="123456789", **kw):
    return Claim(kind="SERIAL_NUMBER", value=value, verification="VERIFIED", source="MANUAL", **kw)


def identity(value="123456789", kind="SERIAL_NUMBER", checked=True, **kw):
    return IdentityEvidence(
        candidate=IdentifierCandidate(
            kind=kind,
            raw_value=value,
            normalized_value=value,
            source="MANUAL",
            line_indices=(0,),
        ),
        human_checked=checked,
        manufacturer_id=MAKER if kind == "SERIAL_NUMBER" else None,
        **kw,
    )


def visual(status="KNOWN_MODEL_CANDIDATE", calibrated=True):
    return SearchResult(
        status=status,
        reason="fixture",
        index_id=None,
        generation_version=1,
        encoder=None,
        calibrated=calibrated,
        candidates=(
            ModelCandidate(
                device_model_id=MODEL,
                rank=1,
                similarity=0.99,
                reference_image_snapshot_id=UUID(int=99),
            ),
        ),
    )


def run(units=(), identifiers=(), **kw):
    return fuse_evidence(
        FusionInput(
            snapshot_at=NOW,
            observed_at=NOW,
            units=units,
            identifiers=identifiers,
            complete_snapshot=True,
            **kw,
        )
    )


def test_sprint_example_damaged_serial_lounge_is_probable():
    result = run(
        (unit(current_location_id=LOUNGE), unit(11, current_location_id=LOBBY)),
        visual=visual(),
        observed_location_id=LOUNGE,
    )
    assert result.status == "PROBABLE_ASSET"
    assert result.candidates[0].asset_id == UUID(int=10)
    assert result.requires_review


def test_identical_same_location_ambiguous():
    assert (
        run(
            (unit(current_location_id=LOUNGE), unit(11, current_location_id=LOUNGE)),
            visual=visual(),
            observed_location_id=LOUNGE,
        ).status
        == "AMBIGUOUS"
    )


def test_location_alone_never_selects_identity():
    assert run((unit(current_location_id=LOUNGE),), observed_location_id=LOUNGE).status == "UNKNOWN"


@pytest.mark.parametrize(
    "status,calibrated",
    [("UNCERTAIN", False), ("UNKNOWN_MODEL", True), ("KNOWN_MODEL_CANDIDATE", False)],
)
def test_visual_gate(status, calibrated):
    result = run((unit(),), visual=visual(status, calibrated))
    assert result.status == "UNKNOWN"
    assert result.model_candidates == (MODEL,)


def test_checked_unique_identifier_still_requires_human_review():
    result = run((unit(claims=(claim(),)),), (identity(),))
    assert result.status == "PROBABLE_ASSET"
    assert "HUMAN_REVIEW_REQUIRED_NO_AUTO_VERIFICATION" in result.reasons
    assert result.requires_review


def test_sn_matching_location_mismatch_conflict():
    result = run(
        (unit(claims=(claim(),), current_location_id=LOBBY),),
        (identity(),),
        observed_location_id=LOUNGE,
    )
    assert result.status == "CONFLICT"
    assert "OFFICIAL_LOCATION_CONFLICT" in result.candidates[0].reasons


def test_two_identifiers_disagree():
    assert (
        run(
            (unit(claims=(claim(),)), unit(11, claims=(claim("987654321"),))),
            (identity(), identity("987654321")),
        ).status
        == "CONFLICT"
    )


def test_checked_unmatched_identifier_cannot_be_dropped():
    assert run((unit(claims=(claim(),)),), (identity(), identity("987654321"))).status == "CONFLICT"


def test_collision_including_archived_unit_is_ambiguous():
    result = run(
        (unit(claims=(claim(),)), unit(11, claims=(claim(),), archived=True)), (identity(),)
    )
    assert result.status == "AMBIGUOUS"
    assert len(result.candidates) == 2


def test_manufacturer_scope():
    foreign = unit(11, claims=(claim(),)).model_copy(update={"manufacturer_id": OTHER})
    result = run((unit(claims=(claim(),)), foreign), (identity(),))
    assert len(result.candidates) == 1


def test_missing_manufacturer_not_strong():
    evidence = identity().model_copy(update={"manufacturer_id": None})
    result = run(
        (unit(claims=(claim(),), current_location_id=LOBBY),),
        (evidence,),
        observed_location_id=LOUNGE,
    )
    assert result.status == "PROBABLE_ASSET"
    assert "SERIAL_MANUFACTURER_REQUIRED" in result.reasons


@pytest.mark.parametrize("kind", ["MAC", "BSSID", "MODEL"])
def test_generic_mac_bssid_model_do_not_identify(kind):
    assert run((unit(),), (identity("00:11:22:33:44:55", kind=kind),)).status == "UNKNOWN"


@pytest.mark.parametrize("value", ["00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF", "01:11:22:33:44:55"])
def test_non_device_mac_rejected(value):
    assert run((unit(),), (identity(value, kind="MAC_LAN"),)).status == "UNKNOWN"


def test_mac_type_exact():
    stored = Claim(
        kind="MAC_WLAN", value="00:11:22:33:44:55", verification="VERIFIED", source="CONTROLLER"
    )
    assert (
        run((unit(claims=(stored,)),), (identity(stored.value, kind="MAC_LAN"),)).status
        == "UNKNOWN"
    )
    assert (
        run((unit(claims=(stored,)),), (identity(stored.value, kind="MAC_WLAN"),)).status
        == "PROBABLE_ASSET"
    )


def test_raw_ocr_without_label_check_not_strong():
    evidence = identity(checked=False)
    result = run(
        (unit(claims=(claim(),), current_location_id=LOBBY),),
        (evidence,),
        observed_location_id=LOUNGE,
    )
    assert result.status == "PROBABLE_ASSET"
    assert "LABEL_REVIEW_REQUIRED" in result.reasons


def test_ocr_manual_integration_keeps_evidence_immutable():
    ocr = read_label(None, None, None, ManualCorrection(corrected_text="SN: 123456789"))
    before = ocr.model_dump_json()
    evidence = IdentityEvidence(candidate=ocr.manual_candidates[0], manufacturer_id=MAKER)
    result = run((unit(claims=(claim(),)),), (evidence,))
    assert result.status == "PROBABLE_ASSET"
    assert ocr.model_dump_json() == before
    assert "LABEL_REVIEW_REQUIRED" in result.reasons


def test_model_identifier_conflict_not_filtered_away():
    foreign = unit(claims=(claim(),)).model_copy(update={"device_model_id": OTHER})
    assert run((foreign,), (identity(),), visual=visual()).status == "CONFLICT"


def test_old_observation_does_not_conflict_with_later_placement():
    data = FusionInput(
        snapshot_at=NOW,
        observed_at=NOW - timedelta(days=2),
        observed_location_id=LOUNGE,
        identifiers=(identity(),),
        complete_snapshot=True,
        units=(
            unit(
                claims=(claim(),),
                current_location_id=LOBBY,
                location_verified_at=NOW - timedelta(days=1),
            ),
        ),
    )
    assert fuse_evidence(data).status == "PROBABLE_ASSET"


@pytest.mark.parametrize("field", ["latest_observation", "approved_location"])
def test_history_mismatch_and_staleness(field):
    event = LocationEvidence(location_id=LOBBY, observed_at=NOW)
    result = run(
        (unit(claims=(claim(),), current_location_id=LOUNGE, **{field: event}),),
        (identity(),),
        observed_location_id=LOUNGE,
    )
    assert result.status == "CONFLICT"
    stale = event.model_copy(update={"observed_at": NOW - timedelta(days=2)})
    assert (
        run(
            (
                unit(
                    claims=(claim(),),
                    current_location_id=LOUNGE,
                    location_verified_at=NOW - timedelta(days=1),
                    **{field: stale},
                ),
            ),
            (identity(),),
            observed_location_id=LOUNGE,
        ).status
        == "PROBABLE_ASSET"
    )


def test_permutation_stable_and_input_unchanged():
    units = (unit(11), unit(10))
    result = run(units, visual=visual())
    assert result == run(tuple(reversed(units)), visual=visual())
    assert result.candidates[0].asset_id == UUID(int=10)
    assert units[0].asset_version == 1


@pytest.mark.parametrize(
    "update",
    [
        {"complete_snapshot": False},
        {"units": (unit(), unit())},
        {"observed_at": NOW + timedelta(days=1)},
        {"unknown": True},
        {"snapshot_at": NOW.replace(tzinfo=None)},
        {"units": tuple(unit(i + 10) for i in range(501))},
    ],
)
def test_snapshot_validation(update):
    values = dict(snapshot_at=NOW, observed_at=NOW, complete_snapshot=True)
    with pytest.raises(ValidationError):
        FusionInput(**(values | update))


def test_serial_case_sensitive_and_no_fuzzy_repair():
    assert run((unit(claims=(claim("ABC1"),)),), (identity("abc1"),)).status == "UNKNOWN"


def test_unverified_master_not_promoted():
    stored = claim().model_copy(update={"verification": "UNVERIFIED"})
    result = run((unit(claims=(stored,)),), (identity(),))
    assert result.status == "PROBABLE_ASSET"
    assert "MASTER_CLAIM_REVIEW_REQUIRED" in result.reasons


def test_checked_unmatched_overrides_visual_location_guess():
    result = run(
        (unit(current_location_id=LOUNGE),),
        (identity(),),
        visual=visual(),
        observed_location_id=LOUNGE,
    )
    assert result.status == "UNKNOWN"
    assert result.candidates == ()
    assert "CHECKED_IDENTIFIER_UNMATCHED" in result.reasons
    assert result.model_status == "KNOWN_MODEL_CANDIDATE"


def test_multiple_new_identifiers_support_unknown_without_false_conflict():
    result = run(
        (unit(),), (identity(), identity("00:11:22:33:44:55", kind="MAC_LAN")), visual=visual()
    )
    assert result.status == "UNKNOWN"
    assert result.candidates == ()
