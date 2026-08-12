import os
import yaml
import hashlib
import json
from typing import Dict, Any, List, Optional
from core.models import Policy, PolicyRule, PolicyMetadata

ACTION_SEVERITY = {
    "block": 3,
    "redact": 2,
    "allow": 1
}

def validate_inheritance(base_rule: PolicyRule, child_rule: PolicyRule) -> None:
    """
    Ensure the child rule does not weaken the base rule.
    Raises ValueError if child rule is less restrictive than base rule.
    """
    # 1. Action safety
    base_action_type = base_rule.action.type.lower()
    child_action_type = child_rule.action.type.lower()
    base_sev = ACTION_SEVERITY.get(base_action_type, 0)
    child_sev = ACTION_SEVERITY.get(child_action_type, 0)
    if child_sev < base_sev:
        raise ValueError(
            f"Rule '{child_rule.id}' weakens action from '{base_rule.action.type}' to '{child_rule.action.type}'."
        )

    # 2. Threshold safety (e.g. toxicity threshold)
    # Lower threshold is stricter (blocks more). Child cannot have a higher threshold than base.
    base_thresh = base_rule.check.threshold
    child_thresh = child_rule.check.threshold
    if base_thresh is not None:
        if child_thresh is None:
            raise ValueError(
                f"Rule '{child_rule.id}' weakens constraint: base requires threshold '{base_thresh}' but child does not specify it."
            )
        if child_thresh > base_thresh:
            raise ValueError(
                f"Rule '{child_rule.id}' weakens threshold from {base_thresh} to {child_thresh} (must be <=)."
            )

    # 3. Semantic threshold safety
    # Lower threshold is stricter (blocks more). Child cannot have a higher threshold than base.
    base_sem_thresh = base_rule.check.semantic_threshold
    child_sem_thresh = child_rule.check.semantic_threshold
    if base_sem_thresh is not None:
        if child_sem_thresh is None:
            raise ValueError(
                f"Rule '{child_rule.id}' weakens constraint: base requires semantic threshold '{base_sem_thresh}' but child does not specify it."
            )
        if child_sem_thresh > base_sem_thresh:
            raise ValueError(
                f"Rule '{child_rule.id}' weakens semantic threshold from {base_sem_thresh} to {child_sem_thresh} (must be <=)."
            )

    # 4. Topics safety (denied topics)
    # Child must not remove any topics defined in base. It can add topics.
    base_topics = base_rule.check.topics
    child_topics = child_rule.check.topics
    if base_topics:
        if not child_topics:
            raise ValueError(
                f"Rule '{child_rule.id}' weakens constraint: base denies topics {base_topics} but child denies none."
            )
        base_set = set(t.lower() for t in base_topics)
        child_set = set(t.lower() for t in child_topics)
        missing_topics = base_set - child_set
        if missing_topics:
            raise ValueError(
                f"Rule '{child_rule.id}' weakens constraint: child removes base denied topics: {list(missing_topics)}."
            )

    # 5. PII entities safety (denied entities)
    # Child must not remove any PII entities defined in base. It can add entities.
    base_entities = base_rule.check.entities
    child_entities = child_rule.check.entities
    if base_entities:
        if not child_entities:
            raise ValueError(
                f"Rule '{child_rule.id}' weakens constraint: base requires entities {base_entities} but child requires none."
            )
        base_set = set(e.lower() for e in base_entities)
        child_set = set(e.lower() for e in child_entities)
        missing_entities = base_set - child_set
        if missing_entities:
            raise ValueError(
                f"Rule '{child_rule.id}' weakens constraint: child removes base required PII entities: {list(missing_entities)}."
            )

class PolicyLoader:
    @staticmethod
    def load_raw_yaml(path: str) -> Dict[str, Any]:
        """Loads yaml dict from file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Policy file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    raise ValueError("Policy file must be a YAML mapping.")
                return data
            except yaml.YAMLError as e:
                raise ValueError(f"Malformed YAML in policy file: {e}")

    @classmethod
    def load_policy(cls, path: str) -> Policy:
        """
        Loads a policy YAML file.
        Resolves inheritance if the policy contains 'extends' reference.
        Validates child constraints against parent constraints.
        """
        raw_data = cls.load_raw_yaml(path)
        
        # 1. Resolve extends
        extends_file = raw_data.get("extends")
        if extends_file:
            # Resolve relative to the child policy file directory
            parent_dir = os.path.dirname(path)
            parent_path = os.path.abspath(os.path.join(parent_dir, extends_file))
            base_policy = cls.load_policy(parent_path)
            
            # Merge logic
            merged_rules: Dict[str, PolicyRule] = {r.id: r for r in base_policy.rules}
            
            child_rules_raw = raw_data.get("rules", [])
            for r_raw in child_rules_raw:
                child_rule = PolicyRule(**r_raw)
                if child_rule.id in merged_rules:
                    # Validate inheritance safety before replacing
                    base_rule = merged_rules[child_rule.id]
                    validate_inheritance(base_rule, child_rule)
                merged_rules[child_rule.id] = child_rule
            
            # Combine metadata
            base_metadata = base_policy.metadata.model_dump() if base_policy.metadata else {}
            child_metadata = raw_data.get("metadata", {})
            combined_metadata = {**base_metadata, **child_metadata}
            
            policy_data = {
                "version": raw_data.get("version", base_policy.version),
                "extends": extends_file,
                "metadata": combined_metadata,
                "rules": list(merged_rules.values())
            }
            return Policy(**policy_data)
        else:
            # Parse normal policy
            rules_raw = raw_data.get("rules", [])
            rules = [PolicyRule(**r) for r in rules_raw]
            
            metadata_raw = raw_data.get("metadata")
            metadata = PolicyMetadata(**metadata_raw) if metadata_raw else None
            
            return Policy(
                version=str(raw_data.get("version", "1.0")),
                extends=None,
                metadata=metadata,
                rules=rules
            )

    @staticmethod
    def get_policy_hash(policy: Policy) -> str:
        """
        Generates a deterministic SHA-256 hash of the effective policy.
        """
        # Sort and serialize to ensure deterministic output
        policy_dict = policy.model_dump()
        serialized = json.dumps(policy_dict, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
