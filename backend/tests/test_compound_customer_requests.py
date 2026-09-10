from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.agents.turn_models import (
    CompoundRequestedItem,
    SemanticCapabilityDecision,
    SemanticEntityHints,
)
from app.services import agent_chat
from app.services import compound_customer_requests as compound


def _hints(*, requested_items: list[CompoundRequestedItem]) -> SemanticEntityHints:
    return SemanticEntityHints(
        service_query=None,
        branch_query=None,
        doctor_query=None,
        service_id=None,
        service_candidate_ids=[],
        branch_id=None,
        branch_candidate_ids=[],
        doctor_id=None,
        doctor_candidate_ids=[],
        laser_device_key=None,
        package_sessions_count=None,
        requested_items=requested_items,
        appointment_id=None,
        requested_date=None,
        requested_start_time=None,
        not_before_time=None,
        not_after_time=None,
        appointment_reference=None,
    )


def _decision(items: list[CompoundRequestedItem]) -> SemanticCapabilityDecision:
    return SemanticCapabilityDecision(
        domains=["booking"],
        capabilities=[],
        risk_flags=[],
        flow_signal="none",
        package_intent="none",
        entity_hints=_hints(requested_items=items),
        missing_information=[],
        recommended_handoff_category="other",
        recommended_handoff_priority="normal",
        confidence=1.0,
        reason="compound test",
    )


def _appointment(service_id, *, day: str, time: str) -> CompoundRequestedItem:
    return CompoundRequestedItem(
        kind="appointment",
        service_query=None,
        service_id=str(service_id),
        service_candidate_ids=[],
        doctor_query=None,
        doctor_id=None,
        doctor_candidate_ids=[],
        laser_device_key=None,
        package_sessions_count=None,
        requested_date=day,
        requested_start_time=time,
        not_before_time=None,
        not_after_time=None,
        package_intent="avoid_existing",
        missing_information=[],
    )


def _package(service_id, *, device: str, sessions: int) -> CompoundRequestedItem:
    return CompoundRequestedItem(
        kind="package_purchase",
        service_query=None,
        service_id=str(service_id),
        service_candidate_ids=[],
        doctor_query=None,
        doctor_id=None,
        doctor_candidate_ids=[],
        laser_device_key=device,
        package_sessions_count=sessions,
        requested_date=None,
        requested_start_time=None,
        not_before_time=None,
        not_after_time=None,
        package_intent="none",
        missing_information=[],
    )


def test_two_services_remain_two_queued_appointments_and_advance(monkeypatch) -> None:
    workspace_id = uuid4()
    first_service = uuid4()
    second_service = uuid4()
    items = [
        _appointment(first_service, day="2026-09-12", time="14:00"),
        _appointment(second_service, day="2026-09-13", time="15:00"),
    ]
    catalog = {
        "services": [
            {"id": str(first_service), "name": "Facial"},
            {"id": str(second_service), "name": "Underarm"},
        ],
        "doctors": [],
    }

    grounded = compound.ground_compound_requested_items(items, catalog)
    decision = compound.compound_union_decision(_decision(items), grounded)
    first_decision = compound.appointment_decision_from_item(decision, grounded[0])
    state = compound.appointment_item_state(
        grounded[0],
        remaining=grounded[1:],
        total=2,
        completed=0,
        catalog=catalog,
    )
    state["branch_id"] = str(uuid4())
    flow = SimpleNamespace(entity_state=state)
    completed_calls: list[dict] = []

    def fake_transition(_db, current_flow, **changes):
        current_flow.entity_state = changes["entity_state"]
        return current_flow

    monkeypatch.setattr(agent_chat, "build_clinic_catalog", lambda _db, _workspace: catalog)
    monkeypatch.setattr(agent_chat, "transition_flow", fake_transition)
    monkeypatch.setattr(
        agent_chat,
        "complete_flow",
        lambda *args, **kwargs: completed_calls.append(kwargs),
    )

    next_flow, next_item = agent_chat._advance_compound_booking_flow(
        db=object(),
        flow=flow,
        workspace=SimpleNamespace(id=workspace_id, primary_branch_id=uuid4()),
        run_id=uuid4(),
        result={"ok": True, "appointment": {"service": "Facial"}},
    )

    assert first_decision.entity_hints.service_id == str(first_service)
    assert next_flow is flow
    assert next_item is not None
    assert next_item.service_id == str(second_service)
    assert flow.entity_state["service_id"] == str(second_service)
    assert compound.queue_from_flow_state(flow.entity_state) == []
    assert compound.compound_progress(flow.entity_state) == (1, 2)
    assert completed_calls == []


def test_two_packages_are_validated_then_committed_once_with_zero_payment(monkeypatch) -> None:
    first_service = uuid4()
    second_service = uuid4()
    first_offer_id = uuid4()
    second_offer_id = uuid4()
    offers = [
        SimpleNamespace(
            id=first_offer_id,
            service_id=first_service,
            service_name="Full Body",
            device_key="candela_gentle",
            device_name="Candela Gentle",
            sessions_count=6,
            price_minor=600_000,
            currency="EGP",
        ),
        SimpleNamespace(
            id=second_offer_id,
            service_id=second_service,
            service_name="Underarm",
            device_key="prime_lase",
            device_name="Prime Lase",
            sessions_count=3,
            price_minor=120_000,
            currency="EGP",
        ),
    ]
    items = [
        _package(first_service, device="candela_gentle", sessions=6),
        _package(second_service, device="prime_lase", sessions=3),
    ]
    calls: list[dict] = []

    class FakeDB:
        def __init__(self) -> None:
            self.commits = 0
            self.rollbacks = 0
            self.added: list[object] = []

        def add(self, value) -> None:
            self.added.append(value)

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

    db = FakeDB()
    monkeypatch.setattr(compound, "list_package_offers", lambda *args, **kwargs: offers)

    def fake_purchase(_db, **kwargs):
        calls.append(kwargs)
        offer = next(item for item in offers if item.id == kwargs["offer_id"])
        return SimpleNamespace(
            id=uuid4(),
            service_id=offer.service_id,
            laser_device_key=offer.device_key,
            sessions_purchased=offer.sessions_count,
            sale_price_minor=offer.price_minor,
        )

    monkeypatch.setattr(compound, "purchase_package_offer", fake_purchase)
    result = compound.purchase_compound_package_batch(
        db,
        workspace=SimpleNamespace(id=uuid4()),
        patient=SimpleNamespace(id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        run_id=uuid4(),
        items=items,
    )

    assert result.ok is True
    assert result.purchased_count == 2
    assert len(calls) == 2
    assert all(call["amount_paid_minor"] == 0 for call in calls)
    assert all(call["payment_method"] == "unknown" for call in calls)
    assert db.commits == 1
    assert db.rollbacks == 0
    assert "Full Body" in result.reply
    assert "Underarm" in result.reply
    assert "ما سجلتش أي دفعة" in result.reply


def test_mixed_package_and_service_keeps_appointment_after_package_batch(monkeypatch) -> None:
    package_service = uuid4()
    appointment_service = uuid4()
    package_item = _package(package_service, device="candela_gentle", sessions=6)
    appointment_item = _appointment(
        appointment_service,
        day="2026-09-14",
        time="16:00",
    )
    items = [package_item, appointment_item]
    catalog = {
        "services": [
            {"id": str(package_service), "name": "Full Body"},
            {"id": str(appointment_service), "name": "Facial"},
        ],
        "doctors": [],
    }
    grounded = compound.ground_compound_requested_items(items, catalog)
    union = compound.compound_union_decision(_decision(items), grounded)

    assert [item.kind for item in grounded] == ["package_purchase", "appointment"]
    assert "package_purchase" in union.capabilities
    assert "appointment_creation" in union.capabilities

    purchased: list[object] = []
    monkeypatch.setattr(
        compound,
        "list_package_offers",
        lambda *args, **kwargs: [
            SimpleNamespace(
                id=uuid4(),
                service_id=package_service,
                service_name="Full Body",
                device_key="candela_gentle",
                device_name="Candela Gentle",
                sessions_count=6,
                price_minor=600_000,
                currency="EGP",
            )
        ],
    )

    class FakeDB:
        def add(self, value) -> None:
            purchased.append(value)

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            raise AssertionError("mixed happy path should not roll back")

    def fake_purchase(_db, **kwargs):
        return SimpleNamespace(
            id=uuid4(),
            service_id=package_service,
            laser_device_key="candela_gentle",
            sessions_purchased=6,
            sale_price_minor=600_000,
        )

    monkeypatch.setattr(compound, "purchase_package_offer", fake_purchase)
    package_result = compound.purchase_compound_package_batch(
        FakeDB(),
        workspace=SimpleNamespace(id=uuid4()),
        patient=SimpleNamespace(id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        run_id=uuid4(),
        items=compound.package_items(grounded),
    )
    appointment_decision = compound.appointment_decision_from_item(
        union,
        compound.appointment_items(grounded)[0],
    )

    assert package_result.ok is True
    assert package_result.purchased_count == 1
    assert appointment_decision.entity_hints.service_id == str(appointment_service)
    assert appointment_decision.entity_hints.requested_date == "2026-09-14"
    assert appointment_decision.entity_hints.requested_start_time == "16:00"
    assert appointment_decision.package_intent == "avoid_existing"
    assert appointment_decision.capabilities == [
        "availability_discovery",
        "appointment_creation",
    ]
