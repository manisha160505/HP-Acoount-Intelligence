"""Client-facing wording that is shared between features.

Client rule (approved 21 Oct): nothing the client reads may carry gap or error
wording ("Unknown", "N/A", "Not available", "failed", fault lists...). A value
that is absent is published empty and the UI hides it; the reason stays in
internal fields (data_gaps, unavailable_reason, detection_note, generation).
Where an action the user started cannot complete, the one line they see is
this neutral one - the same text as the frontend's `ACTION_FAILED`
(hp-frontend/src/lib/uiCopy.ts).
"""

ACTION_FAILED = "Something went wrong. Please try again."
