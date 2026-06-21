import copy

ALLOWED_OVERRIDE_FIELDS = {
    "text",
    "hint",
    "explanation",
    "options",
    "tables",
    "option_table",
    "image_url",
    "imageUrls",
    "image_assets",
    "subject",
    "system",
    "discipline",
    "rendering_flag",
    "suppressImages",
}


class RenderOverrideValidationError(ValueError):
    pass


def validate_override_changes(changes):
    if not isinstance(changes, dict) or not changes:
        raise RenderOverrideValidationError("changes must be a non-empty object")
    unknown = sorted(set(changes.keys()) - ALLOWED_OVERRIDE_FIELDS)
    if unknown:
        raise RenderOverrideValidationError(
            f"Unsupported override field(s): {', '.join(unknown)}"
        )
    if "text" in changes and not isinstance(changes["text"], str):
        raise RenderOverrideValidationError("text must be a string")
    if "hint" in changes and not isinstance(changes["hint"], str):
        raise RenderOverrideValidationError("hint must be a string")
    if "explanation" in changes and not isinstance(changes["explanation"], str):
        raise RenderOverrideValidationError("explanation must be a string")
    if "image_url" in changes and not isinstance(changes["image_url"], str):
        raise RenderOverrideValidationError("image_url must be a string")
    if "imageUrls" in changes:
        if not isinstance(changes["imageUrls"], list) or not all(
            isinstance(item, str) for item in changes["imageUrls"]
        ):
            raise RenderOverrideValidationError("imageUrls must be an array of strings")
    if "image_assets" in changes and not isinstance(changes["image_assets"], list):
        raise RenderOverrideValidationError("image_assets must be an array")
    if "options" in changes and not isinstance(changes["options"], list):
        raise RenderOverrideValidationError("options must be an array")
    if "tables" in changes and not isinstance(changes["tables"], list):
        raise RenderOverrideValidationError("tables must be an array")
    if (
        "option_table" in changes
        and changes["option_table"] is not None
        and not isinstance(changes["option_table"], dict)
    ):
        raise RenderOverrideValidationError("option_table must be an object or null")
    if (
        "rendering_flag" in changes
        and changes["rendering_flag"] is not None
        and not isinstance(changes["rendering_flag"], dict)
    ):
        raise RenderOverrideValidationError("rendering_flag must be an object or null")
    if "suppressImages" in changes and not isinstance(changes["suppressImages"], bool):
        raise RenderOverrideValidationError("suppressImages must be a boolean")
    for key in ("subject", "system", "discipline"):
        if key in changes and not isinstance(changes[key], str):
            raise RenderOverrideValidationError(f"{key} must be a string")
    return changes


def apply_render_override(question, override):
    if not question:
        return question, None
    if not override or not override.get("active", True):
        return copy.deepcopy(question), None
    question = copy.deepcopy(question)
    changes = copy.deepcopy(override.get("changes") or {})
    suppress_images = bool(changes.pop("suppressImages", False))
    for key, value in changes.items():
        question[key] = value
    if suppress_images:
        question["image_url"] = ""
        question["imageUrls"] = []
        question["image_assets"] = []
    return question, {
        "questionId": override.get("question_id"),
        "reason": override.get("reason") or "",
        "updatedBy": override.get("updated_by") or "",
        "updatedAt": override.get("updated_at"),
    }
