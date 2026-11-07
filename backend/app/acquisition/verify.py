from app.acquisition.model_recall import ModelRecallClaim
from app.domain import Chunk, Provenance


class RecallVerificationService:
    """Verifies and promotes Tier-3 model recall claims against Tier-1/2 authoritative evidence."""

    @staticmethod
    def verify_and_promote(
        claim: ModelRecallClaim,
        confirming_chunk: Chunk,
    ) -> Provenance | None:
        """Cross-check an unverified claim against an ingested chunk.

        If the chunk contains supporting facts for the claim's subject and object,
        the claim is promoted from Tier 3 to verified status.
        """
        text = confirming_chunk.text.lower()
        sub_clean = claim.subject.lower().strip()
        obj_clean = claim.object.lower().strip()

        has_subject = sub_clean in text
        has_object = obj_clean in text

        # Both subject and object must be substantiated by the authoritative chunk
        if has_subject and has_object:
            confirmation_uri = (
                f"{confirming_chunk.provenance.source_uri}#{confirming_chunk.chunk_id}"
            )
            return claim.provenance.promote(confirmation_uri=confirmation_uri)

        return None
