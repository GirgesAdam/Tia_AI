from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.channel_connection import ChannelConnection
from app.models.channel_identity import ChannelIdentity
from app.models.conversation import Conversation
from app.models.crm_campaign import CRMCampaign, CRMCampaignRecipient
from app.models.crm_cohort import CRMCohort, CRMCohortMember
from app.models.message import Message
from app.models.message_dispatch import MessageDispatch
from app.models.patient import Patient
from app.models.workspace import Workspace
from app.services.activity import record_activity_event
from app.services.conversation_ownership import record_outbound_activity

MAX_CAMPAIGN_RECIPIENTS = 25
_ALLOWED_PARAMETER_KEYS = frozenset({"patient_first_name", "clinic_name", "cohort_name"})


class CRMCampaignError(ValueError):
    pass


def _campaign_connection(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    active_required: bool = True,
) -> ChannelConnection:
    connection = db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.workspace_id == workspace_id,
            ChannelConnection.id == connection_id,
        )
    )
    if connection is None:
        raise CRMCampaignError("WhatsApp connection not found in this workspace.")
    if connection.channel != "whatsapp":
        raise CRMCampaignError("CRM campaigns currently support WhatsApp only.")
    if active_required and connection.status != "active":
        raise CRMCampaignError("WhatsApp connection must be active before campaign confirmation.")
    return connection


def _route_identity(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    patient_id: UUID,
) -> ChannelIdentity | None:
    return db.scalar(
        select(ChannelIdentity).where(
            ChannelIdentity.workspace_id == workspace_id,
            ChannelIdentity.channel_connection_id == connection_id,
            ChannelIdentity.patient_id == patient_id,
        )
    )


def _eligibility(patient: Patient | None, identity: ChannelIdentity | None) -> tuple[str, str | None]:
    if patient is None or patient.status != "active":
        return "skipped_inactive", "patient_not_active"
    if not patient.marketing_consent:
        return "skipped_no_consent", "marketing_consent_required"
    if identity is None:
        return "skipped_no_route", "whatsapp_identity_missing"
    return "eligible", None


def prepare_cohort_campaign(
    db: Session,
    *,
    workspace_id: UUID,
    cohort_id: UUID,
    created_by_user_id: UUID,
    request_id: UUID,
    name: str,
    channel_connection_id: UUID,
    template_name: str,
    template_language: str,
    body_parameter_keys: list[str],
    rate_limit_per_minute: int,
) -> CRMCampaign:
    name = " ".join(name.split())
    template_name = template_name.strip()
    template_language = template_language.strip()
    if not name or not template_name or not template_language:
        raise CRMCampaignError("Campaign name and WhatsApp template details are required.")
    if not 1 <= rate_limit_per_minute <= 60:
        raise CRMCampaignError("Campaign rate limit must be between 1 and 60 messages per minute.")
    if len(body_parameter_keys) != len(set(body_parameter_keys)):
        raise CRMCampaignError("Campaign template parameter keys cannot contain duplicates.")
    if any(key not in _ALLOWED_PARAMETER_KEYS for key in body_parameter_keys):
        raise CRMCampaignError("Campaign template parameter key is not supported.")

    existing = db.scalar(
        select(CRMCampaign).where(
            CRMCampaign.workspace_id == workspace_id,
            CRMCampaign.request_key == str(request_id),
        )
    )
    if existing is not None:
        return existing

    cohort = db.scalar(
        select(CRMCohort).where(
            CRMCohort.workspace_id == workspace_id,
            CRMCohort.id == cohort_id,
        )
    )
    if cohort is None:
        raise CRMCampaignError("CRM cohort not found in this workspace.")
    if cohort.status != "active":
        raise CRMCampaignError("Only active CRM cohorts can prepare campaigns.")
    if cohort.member_count < 1 or cohort.member_count > MAX_CAMPAIGN_RECIPIENTS:
        raise CRMCampaignError("CRM cohort size is outside the campaign safety limit.")

    _campaign_connection(
        db,
        workspace_id=workspace_id,
        connection_id=channel_connection_id,
        active_required=False,
    )

    members = list(
        db.scalars(
            select(CRMCohortMember)
            .where(
                CRMCohortMember.workspace_id == workspace_id,
                CRMCohortMember.cohort_id == cohort_id,
            )
            .order_by(CRMCohortMember.rank, CRMCohortMember.id)
        ).all()
    )
    if len(members) != cohort.member_count:
        raise CRMCampaignError("CRM cohort membership snapshot is inconsistent.")

    patient_ids = [member.patient_id for member in members]
    patients = {
        patient.id: patient
        for patient in db.scalars(
            select(Patient).where(
                Patient.workspace_id == workspace_id,
                Patient.id.in_(patient_ids),
            )
        ).all()
    }
    identities = {
        identity.patient_id: identity
        for identity in db.scalars(
            select(ChannelIdentity).where(
                ChannelIdentity.workspace_id == workspace_id,
                ChannelIdentity.channel_connection_id == channel_connection_id,
                ChannelIdentity.patient_id.in_(patient_ids),
            )
        ).all()
    }

    eligibility: list[tuple[CRMCohortMember, str, str | None]] = []
    eligible_count = 0
    for member in members:
        status, reason = _eligibility(patients.get(member.patient_id), identities.get(member.patient_id))
        if status == "eligible":
            eligible_count += 1
        eligibility.append((member, status, reason))

    campaign = CRMCampaign(
        workspace_id=workspace_id,
        cohort_id=cohort_id,
        channel_connection_id=channel_connection_id,
        created_by_user_id=created_by_user_id,
        request_key=str(request_id),
        name=name,
        status="draft",
        template_name=template_name,
        template_language=template_language,
        body_parameter_keys_json=list(body_parameter_keys),
        rate_limit_per_minute=rate_limit_per_minute,
        recipient_count=len(members),
        eligible_count=eligible_count,
    )
    savepoint = db.begin_nested()
    db.add(campaign)
    try:
        db.flush([campaign])
        savepoint.commit()
    except IntegrityError as exc:
        savepoint.rollback()
        existing = db.scalar(
            select(CRMCampaign).where(
                CRMCampaign.workspace_id == workspace_id,
                CRMCampaign.request_key == str(request_id),
            )
        )
        if existing is not None:
            return existing
        raise CRMCampaignError("CRM campaign draft could not be created because of a concurrent conflict.") from exc

    for member, status, reason in eligibility:
        identity = identities.get(member.patient_id)
        db.add(
            CRMCampaignRecipient(
                workspace_id=workspace_id,
                campaign_id=campaign.id,
                patient_id=member.patient_id,
                rank=member.rank,
                status=status,
                reason=reason,
                channel_identity_id=identity.id if identity is not None else None,
            )
        )
    db.flush()
    record_activity_event(
        db,
        workspace_id=workspace_id,
        actor_type="staff",
        actor_user_id=created_by_user_id,
        action="crm_campaign.prepared",
        entity_type="crm_campaign",
        entity_id=campaign.id,
        summary="WhatsApp CRM cohort campaign prepared",
        metadata={
            "cohort_id": cohort_id,
            "recipient_count": len(members),
            "eligible_count": eligible_count,
            "rate_limit_per_minute": rate_limit_per_minute,
            "template_name": template_name,
        },
    )
    db.commit()
    db.refresh(campaign)
    return campaign


def _body_parameters(
    *,
    keys: list[str],
    patient: Patient,
    workspace: Workspace | None,
    cohort: CRMCohort,
) -> list[str]:
    values = {
        "patient_first_name": (patient.first_name or "العميل")[:256],
        "clinic_name": ((workspace.name if workspace is not None else "العيادة") or "العيادة")[:256],
        "cohort_name": cohort.name[:256],
    }
    return [values[key] for key in keys]


def _existing_or_new_conversation(
    db: Session,
    *,
    workspace_id: UUID,
    patient_id: UUID,
    connection: ChannelConnection,
    identity: ChannelIdentity,
    now: datetime,
) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.patient_id == patient_id,
            Conversation.channel_connection_id == connection.id,
        )
        .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.started_at.desc())
        .limit(1)
    )
    if conversation is not None:
        return conversation
    conversation = Conversation(
        workspace_id=workspace_id,
        patient_id=patient_id,
        channel="whatsapp",
        status="open",
        owner_type="ai",
        unread_count=0,
        external_conversation_id=identity.external_user_id,
        channel_connection_id=connection.id,
        started_at=now,
        last_message_at=None,
        ownership_changed_at=now,
    )
    db.add(conversation)
    db.flush()
    return conversation


def _confirmation_result(campaign: CRMCampaign, recipients: list[CRMCampaignRecipient]) -> dict:
    queued = sum(1 for row in recipients if row.status in {"queued", "processing", "sent", "delivered", "read", "failed", "cancelled"})
    cancelled = sum(1 for row in recipients if row.status.startswith("cancelled_"))
    return {
        "campaign_id": campaign.id,
        "confirmation_id": UUID(campaign.confirmation_key) if campaign.confirmation_key else UUID(int=0),
        "recipient_count": campaign.recipient_count,
        "preview_eligible_count": campaign.eligible_count,
        "queued_count": queued,
        "cancelled_before_queue": cancelled,
        "status": "confirmed",
    }


def confirm_cohort_campaign(
    db: Session,
    *,
    workspace_id: UUID,
    campaign_id: UUID,
    confirmation_id: UUID,
    actor_user_id: UUID,
    now: datetime | None = None,
) -> dict:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    campaign = db.scalar(
        select(CRMCampaign)
        .where(
            CRMCampaign.workspace_id == workspace_id,
            CRMCampaign.id == campaign_id,
        )
        .with_for_update()
    )
    if campaign is None:
        raise CRMCampaignError("CRM campaign not found in this workspace.")
    recipients = list(
        db.scalars(
            select(CRMCampaignRecipient)
            .where(
                CRMCampaignRecipient.workspace_id == workspace_id,
                CRMCampaignRecipient.campaign_id == campaign_id,
            )
            .order_by(CRMCampaignRecipient.rank, CRMCampaignRecipient.id)
            .with_for_update()
        ).all()
    )
    if campaign.status == "confirmed":
        return _confirmation_result(campaign, recipients)
    if campaign.status != "draft":
        raise CRMCampaignError("Only draft CRM campaigns can be confirmed.")
    if len(recipients) != campaign.recipient_count:
        raise CRMCampaignError("CRM campaign recipient snapshot is inconsistent.")
    if campaign.eligible_count == 0:
        raise CRMCampaignError("Campaign has no eligible recipients to send.")

    connection = _campaign_connection(
        db,
        workspace_id=workspace_id,
        connection_id=campaign.channel_connection_id,
        active_required=True,
    )
    cohort = db.scalar(
        select(CRMCohort).where(
            CRMCohort.workspace_id == workspace_id,
            CRMCohort.id == campaign.cohort_id,
        )
    )
    if cohort is None or cohort.status != "active":
        raise CRMCampaignError("CRM cohort is no longer active.")
    workspace = db.get(Workspace, workspace_id)
    parameter_keys = list(campaign.body_parameter_keys_json or [])
    spacing_seconds = max(1, ceil(60 / campaign.rate_limit_per_minute))
    queued_index = 0
    cancelled_before_queue = 0

    for recipient in recipients:
        # A preview-skipped member never becomes newly eligible during confirmation.
        # This preserves the audience that staff actually reviewed.
        if recipient.status != "eligible":
            continue
        patient = db.scalar(
            select(Patient).where(
                Patient.workspace_id == workspace_id,
                Patient.id == recipient.patient_id,
            )
        )
        identity = _route_identity(
            db,
            workspace_id=workspace_id,
            connection_id=connection.id,
            patient_id=recipient.patient_id,
        )
        status, reason = _eligibility(patient, identity)
        if status != "eligible":
            recipient.status = {
                "skipped_no_consent": "cancelled_no_consent",
                "skipped_inactive": "cancelled_inactive",
                "skipped_no_route": "cancelled_no_route",
            }[status]
            recipient.reason = reason
            cancelled_before_queue += 1
            continue
        assert patient is not None and identity is not None

        conversation = _existing_or_new_conversation(
            db,
            workspace_id=workspace_id,
            patient_id=patient.id,
            connection=connection,
            identity=identity,
            now=current,
        )
        scheduled_at = current + timedelta(seconds=queued_index * spacing_seconds)
        metadata = {
            "source": "crm_cohort_campaign",
            "crm_campaign_id": str(campaign.id),
            "crm_campaign_recipient_id": str(recipient.id),
            "crm_cohort_id": str(campaign.cohort_id),
            "marketing_consent_required": True,
            "whatsapp_template": {
                "name": campaign.template_name,
                "language_code": campaign.template_language,
                "body_parameters": _body_parameters(
                    keys=parameter_keys,
                    patient=patient,
                    workspace=workspace,
                    cohort=cohort,
                ),
            },
        }
        message = Message(
            workspace_id=workspace_id,
            conversation_id=conversation.id,
            channel_connection_id=connection.id,
            sender_type="staff",
            direction="outbound",
            message_type="template",
            content="WhatsApp approved CRM campaign template",
            delivery_status="queued",
            sent_by_user_id=actor_user_id,
            metadata_json=metadata,
        )
        db.add(message)
        db.flush()
        dispatch = MessageDispatch(
            workspace_id=workspace_id,
            channel_connection_id=connection.id,
            message_id=message.id,
            status="queued",
            attempts=0,
            next_attempt_at=scheduled_at,
            metadata_json={
                "conversation_id": str(conversation.id),
                "sender_type": "staff",
                "source": "crm_cohort_campaign",
                "crm_campaign_id": str(campaign.id),
                "crm_campaign_recipient_id": str(recipient.id),
            },
        )
        db.add(dispatch)
        db.flush()
        recipient.status = "queued"
        recipient.reason = None
        recipient.conversation_id = conversation.id
        recipient.channel_identity_id = identity.id
        recipient.message_id = message.id
        recipient.dispatch_id = dispatch.id
        recipient.scheduled_at = scheduled_at
        record_outbound_activity(conversation, now=current)
        queued_index += 1

    if queued_index == 0:
        raise CRMCampaignError("All preview-eligible recipients became ineligible before confirmation.")

    campaign.status = "confirmed"
    campaign.confirmation_key = str(confirmation_id)
    campaign.confirmed_by_user_id = actor_user_id
    campaign.confirmed_at = current
    record_activity_event(
        db,
        workspace_id=workspace_id,
        actor_type="staff",
        actor_user_id=actor_user_id,
        action="crm_campaign.confirmed",
        entity_type="crm_campaign",
        entity_id=campaign.id,
        summary="WhatsApp CRM cohort campaign confirmed",
        metadata={
            "cohort_id": campaign.cohort_id,
            "preview_eligible_count": campaign.eligible_count,
            "queued_count": queued_index,
            "cancelled_before_queue": cancelled_before_queue,
            "rate_limit_per_minute": campaign.rate_limit_per_minute,
            "template_name": campaign.template_name,
            "confirmation_id": confirmation_id,
        },
    )
    db.commit()
    db.refresh(campaign)
    return _confirmation_result(campaign, recipients)


def guard_campaign_dispatch_before_claim(
    db: Session,
    *,
    dispatch: MessageDispatch,
    message: Message,
    conversation: Conversation,
) -> bool:
    metadata = message.metadata_json or {}
    if metadata.get("source") != "crm_cohort_campaign":
        return True
    recipient = db.scalar(
        select(CRMCampaignRecipient).where(
            CRMCampaignRecipient.workspace_id == dispatch.workspace_id,
            CRMCampaignRecipient.dispatch_id == dispatch.id,
        )
    )
    campaign = (
        db.scalar(
            select(CRMCampaign).where(
                CRMCampaign.workspace_id == dispatch.workspace_id,
                CRMCampaign.id == recipient.campaign_id,
            )
        )
        if recipient is not None
        else None
    )
    patient = db.scalar(
        select(Patient).where(
            Patient.workspace_id == dispatch.workspace_id,
            Patient.id == conversation.patient_id,
        )
    )
    status = None
    reason = None
    if campaign is None or campaign.status != "confirmed":
        status, reason = "cancelled", "campaign_not_confirmed"
    elif patient is None or patient.status != "active":
        status, reason = "cancelled_inactive", "patient_not_active"
    elif not patient.marketing_consent:
        status, reason = "cancelled_no_consent", "marketing_consent_withdrawn"
    if status is None:
        if recipient is not None:
            recipient.status = "processing"
            recipient.reason = None
        return True

    dispatch.status = "cancelled"
    dispatch.last_error = reason
    dispatch.next_attempt_at = None
    dispatch.locked_at = None
    message.delivery_status = "cancelled"
    if recipient is not None:
        recipient.status = status
        recipient.reason = reason
    return False


def reconcile_campaign_dispatch(
    db: Session,
    *,
    dispatch: MessageDispatch,
    message: Message | None = None,
) -> None:
    metadata = (message.metadata_json if message is not None else None) or dispatch.metadata_json or {}
    if metadata.get("source") != "crm_cohort_campaign":
        return
    recipient = db.scalar(
        select(CRMCampaignRecipient).where(
            CRMCampaignRecipient.workspace_id == dispatch.workspace_id,
            CRMCampaignRecipient.dispatch_id == dispatch.id,
        )
    )
    if recipient is None:
        return
    if dispatch.status in {"queued", "processing", "sent", "delivered", "read", "failed", "cancelled"}:
        recipient.status = dispatch.status
        if dispatch.status == "failed":
            recipient.reason = (dispatch.last_error or "provider_dispatch_failed")[:120]
        elif dispatch.status not in {"cancelled"}:
            recipient.reason = None
